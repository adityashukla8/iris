"""
IRIS FastAPI application.
Exposes:
  POST /event             — submit an IrisEvent for evaluation
  GET  /stream/alerts     — SSE stream of alerts to dashboard
  GET  /stream/activity   — SSE stream of ADK orchestration events
  GET  /status            — shift stats for dashboard
  GET  /traces            — recent trace feed for dashboard
  GET  /traces/{trace_id} — full trace detail including input/output
  GET  /analytics         — evaluator heatmap + severity timeline stats
  POST /scan              — trigger manual pattern scan
"""
from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# Importing tracing configures Phoenix OTel + ADK instrumentation (side effects).
# Must happen before any agent/genai client is constructed.
from core.phoenix.tracing import force_flush, get_tracer
from core.phoenix.client import phoenix_client, record_event_on_span, span_id_hex

from core.agents.mcp_probe import mcp_probe_agent
from core.alerts import dispatch_alert
from core.config import settings
from core.evaluators.service import EVALUATOR_NAMES, evaluate_event
from core.healing.scan import run_self_healing_scan
from core.state import (
    _activity_subscribers,
    activity_log,
    alert_bus,
    healing_candidates,
    healing_history,
    push_activity,
    recent_traces,
    self_heal_bus,
    shift_stats,
)
from sdk.models import IrisEvent

_probe_session_service = InMemorySessionService()
_probe_runner = Runner(
    agent=mcp_probe_agent,
    app_name="iris-mcp-probe",
    session_service=_probe_session_service,
)
_PROBE_USER_ID = "iris-probe"

SYSTEM_USER_ID = "iris-system"


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(_scheduled_pattern_scan())
    yield


app = FastAPI(title="IRIS Clinical AI Safety Supervisor", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="dashboard/static"), name="static")
templates = Jinja2Templates(directory="dashboard/templates")


@app.post("/event")
async def submit_event(event: IrisEvent) -> dict:
    """
    Receive an IrisEvent from a connected clinical AI agent and run the IRIS
    evaluation deterministically inside an IRIS-owned span. The span carries the
    eval results as attributes; after it is flushed we annotate it via REST so the
    Phoenix Annotations tab is populated for the trace.
    """
    push_activity(f"Event received — {event.agent_name} · {event.query_type}", "info")

    _SEP = "─" * 80
    print(f"\n{_SEP}")
    print(f"[IRIS /event] trace_id={event.trace_id}  agent={event.agent_name}  query_type={event.query_type}")

    tracer = get_tracer()
    try:
        with tracer.start_as_current_span("iris.evaluate") as span:
            record_event_on_span(span, event)
            outcome = await evaluate_event(event, span)
            sid = span_id_hex(span)

        # Span has ended — flush it to Phoenix, then attach annotations by span id.
        force_flush()
        annotated = await phoenix_client.annotate_span(sid, event, outcome.results)

        final_severity = outcome.worst_severity.value
        print(f"[IRIS /event] severity={final_severity}  annotated={annotated}  span={sid}")
        print(_SEP)

        shift_stats["total_traces"] += 1
        if final_severity in ("warning", "critical"):
            shift_stats["hallucinations_caught"] = shift_stats.get("hallucinations_caught", 0) + 1
        if any(r.confidence < 0.6 for r in outcome.results):
            shift_stats["human_escalations"] = shift_stats.get("human_escalations", 0) + 1

        level = "critical" if final_severity == "critical" else "warn" if final_severity == "warning" else "info"
        push_activity(
            f"Evaluation complete — {len(outcome.results)} evaluators · severity: {final_severity}",
            level,
        )

        dispatch_alert(event, outcome)

        evaluations = outcome.to_feed_rows()
        recent_traces.appendleft({
            "trace_id": event.trace_id,
            "span_id": sid,
            "timestamp": event.timestamp.isoformat(),
            "agent_name": event.agent_name,
            "agent_version": event.agent_version,
            "query_type": str(event.query_type),
            "severity": final_severity,
            "input_prompt": event.input_prompt,
            "output_text": event.output_text,
            "retrieved_context": event.retrieved_context.model_dump() if event.retrieved_context else {},
            "surgical_phase": str(event.surgical_phase) if event.surgical_phase else None,
            "latency_ms": event.latency_ms,
            "evaluations": evaluations,
        })

        return {
            "trace_id": event.trace_id,
            "status": "evaluated",
            "severity": final_severity,
            "annotated": annotated,
            "evaluations": evaluations,
        }

    except Exception as exc:
        print(f"[IRIS /event] ERROR: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/scan")
async def trigger_pattern_scan() -> dict:
    """Manually trigger a detect → diagnose → heal scan."""
    return await _run_scan()


@app.get("/stream/alerts")
async def alert_stream():
    """SSE stream of safety alerts for the dashboard."""
    async def event_generator():
        while True:
            try:
                alert = await asyncio.wait_for(alert_bus.get(), timeout=30.0)
                data = json.dumps(alert.model_dump(mode="json"))
                yield f"data: {data}\n\n"
            except asyncio.TimeoutError:
                yield "data: {\"type\": \"heartbeat\"}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/stream/activity")
async def activity_stream():
    """SSE stream of ADK orchestration and healing pipeline events."""
    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    _activity_subscribers.append(q)

    async def event_generator():
        try:
            while True:
                try:
                    evt = await asyncio.wait_for(q.get(), timeout=30.0)
                    yield f"data: {json.dumps(evt)}\n\n"
                except asyncio.TimeoutError:
                    yield "data: {\"type\": \"heartbeat\"}\n\n"
        finally:
            try:
                _activity_subscribers.remove(q)
            except ValueError:
                pass

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/activity")
async def get_activity(limit: int = 100) -> dict:
    """Recent activity log for initial page load."""
    return {"activity": list(activity_log)[:limit]}


@app.get("/status")
async def shift_status() -> dict:
    return {"stats": shift_stats, "connected": True}


@app.get("/traces")
async def get_traces(limit: int = 50) -> dict:
    return {"traces": list(recent_traces)[:limit]}


@app.get("/traces/{trace_id}")
async def get_trace(trace_id: str) -> dict:
    for t in recent_traces:
        if t["trace_id"] == trace_id:
            return {"trace": t}
    raise HTTPException(status_code=404, detail="Trace not found")


@app.get("/healing/candidates")
async def list_healing_candidates() -> dict:
    return {
        "candidates": [c.model_dump(mode="json") for c in healing_candidates],
        "count": len(healing_candidates),
    }


@app.post("/healing/approve/{candidate_id}")
async def approve_healing_candidate(candidate_id: str) -> dict:
    from core.healing.pipeline import approve_candidate
    candidate = await approve_candidate(candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail=f"Candidate {candidate_id} not found")
    return {"candidate_id": candidate_id, "status": candidate.status, "deployed_at": str(candidate.deployed_at)}


@app.post("/healing/reject/{candidate_id}")
async def reject_healing_candidate(candidate_id: str, reason: str = "") -> dict:
    from core.healing.pipeline import reject_candidate
    candidate = await reject_candidate(candidate_id, reason)
    if candidate is None:
        raise HTTPException(status_code=404, detail=f"Candidate {candidate_id} not found")
    return {"candidate_id": candidate_id, "status": candidate.status}


@app.get("/healing/history")
async def healing_history_feed(limit: int = 50) -> dict:
    return {
        "history": [c.model_dump(mode="json") for c in list(healing_history)[:limit]],
        "count": len(healing_history),
    }


@app.get("/analytics")
async def get_analytics() -> dict:
    return {"analytics": _compute_analytics(list(recent_traces))}


@app.post("/simulate")
async def simulate_scenarios(request: Request) -> dict:
    """Run selected ORION demo scenarios through the live evaluation pipeline."""
    body = await request.json()
    scenario_nums: list[int] = body.get("scenarios", list(range(1, 10)))
    delay_ms: float = float(body.get("delay_ms", 1500))

    from demo.mock_agents.bad_orion import SCENARIOS as _DEMO_SCENARIOS  # type: ignore[import]
    import copy

    selected = []
    for num in scenario_nums:
        if 1 <= num <= len(_DEMO_SCENARIOS):
            name, payload = _DEMO_SCENARIOS[num - 1]
            selected.append((num, name, copy.deepcopy(payload)))

    if not selected:
        raise HTTPException(status_code=400, detail="No valid scenario numbers provided")

    asyncio.create_task(_run_simulations(selected, delay_ms))
    return {"status": "started", "scenario_count": len(selected)}


async def _run_simulations(selected: list[tuple], delay_ms: float) -> None:
    total = len(selected)
    push_activity(f"Simulator: starting {total} scenario(s)", "info")
    for i, (num, name, payload) in enumerate(selected, 1):
        payload["trace_id"] = str(uuid.uuid4())
        push_activity(f"Simulator [{i}/{total}]: {name}", "info")
        try:
            event = IrisEvent.model_validate(payload)
            await submit_event(event)
        except Exception as exc:
            push_activity(f"Simulator: scenario {num} error — {str(exc)[:80]}", "critical")
        if delay_ms > 0 and i < total:
            await asyncio.sleep(delay_ms / 1000)
    push_activity(f"Simulator: complete — {total} scenario(s) processed", "heal")


@app.post("/mcp/chat")
async def mcp_chat(request: Request) -> dict:
    """
    Run an ad-hoc natural-language query against Arize Phoenix via the MCP probe agent.
    Each call gets an isolated session — no cross-query context bleed.
    """
    body = await request.json()
    message = (body.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="message required")

    session_id = f"probe-{uuid.uuid4().hex[:12]}"
    await _probe_session_service.create_session(
        app_name="iris-mcp-probe",
        user_id=_PROBE_USER_ID,
        session_id=session_id,
    )

    content = types.Content(role="user", parts=[types.Part(text=message)])
    response_text = ""
    tool_calls: list[dict] = []

    try:
        async for evt in _probe_runner.run_async(
            user_id=_PROBE_USER_ID,
            session_id=session_id,
            new_message=content,
        ):
            parts = getattr(getattr(evt, "content", None), "parts", None) or []
            for part in parts:
                fc = getattr(part, "function_call", None)
                if fc and fc.name:
                    tool_calls.append({"tool": fc.name, "args": dict(fc.args or {})})
                fr = getattr(part, "function_response", None)
                if fr and fr.name:
                    resp = fr.response or {}
                    preview = json.dumps(resp)[:400] if isinstance(resp, dict) else str(resp)[:400]
                    for tc in reversed(tool_calls):
                        if tc["tool"] == fr.name and "result" not in tc:
                            tc["result"] = preview
                            break
            if evt.is_final_response() and evt.content:
                for part in evt.content.parts:
                    if getattr(part, "text", None):
                        response_text = part.text
                        break

        push_activity(f"MCP Probe: {message[:60]} → {len(tool_calls)} tool call(s)", "mcp")
        return {"response": response_text, "tool_calls": tool_calls}

    except Exception as exc:
        return {"response": f"Error: {str(exc)[:300]}", "tool_calls": tool_calls}


@app.get("/", response_class=HTMLResponse)
async def homepage(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "shift_stats": shift_stats,
    })


# ── Helpers ───────────────────────────────────────────────────────────────────

_EVAL_NAMES = EVALUATOR_NAMES


def _compute_analytics(traces: list[dict]) -> dict:
    stats: dict[str, dict] = {
        e: {"runs": 0, "failures": 0, "skipped": 0, "score_sum": 0.0, "critical_count": 0}
        for e in _EVAL_NAMES
    }
    sev_counts: dict[str, int] = {"info": 0, "warning": 0, "critical": 0}
    qt_map: dict[str, dict] = {}
    last_critical_ts: str | None = None

    for t in traces:
        sev = t.get("severity", "info")
        sev_counts[sev] = sev_counts.get(sev, 0) + 1
        if sev == "critical" and last_critical_ts is None:
            last_critical_ts = t.get("timestamp")
        qt = t.get("query_type", "general")
        entry = qt_map.setdefault(qt, {"count": 0, "failures": 0})
        entry["count"] += 1
        if sev != "info":
            entry["failures"] += 1
        for ev in t.get("evaluations", []):
            name = ev.get("evaluator")
            if name not in stats:
                continue
            if ev.get("skipped"):
                stats[name]["skipped"] += 1
                continue
            stats[name]["runs"] += 1
            stats[name]["score_sum"] += ev.get("score", 10.0)
            if not ev.get("passed", True):
                stats[name]["failures"] += 1
            if ev.get("severity") == "critical":
                stats[name]["critical_count"] += 1

    total = len(traces)
    return {
        "evaluator_stats": {
            e: {
                "runs": s["runs"],
                "failures": s["failures"],
                "skipped": s["skipped"],
                "avg_score": round(s["score_sum"] / s["runs"], 2) if s["runs"] else None,
                "critical_count": s["critical_count"],
            }
            for e, s in stats.items()
        },
        "severity_timeline": _bucket_traces_by_minute(traces),
        "query_type_breakdown": {
            qt: {
                "count": v["count"],
                "failure_rate": round(v["failures"] / v["count"], 3) if v["count"] else 0,
            }
            for qt, v in qt_map.items()
        },
        "pass_rate": round(sev_counts.get("info", 0) / total, 3) if total else 1.0,
        "critical_rate": round(sev_counts.get("critical", 0) / total, 3) if total else 0.0,
        "last_critical_ts": last_critical_ts,
    }


def _bucket_traces_by_minute(traces: list[dict]) -> list[dict]:
    """Group traces by wall-clock minute, count severity per bucket. Newest last."""
    buckets: dict[str, dict] = {}
    for t in reversed(traces):  # oldest → newest
        ts = t.get("timestamp", "")
        key = ts[:16] if len(ts) >= 16 else ts       # "2026-05-27T12:34"
        label = ts[11:16] if len(ts) > 15 else ts    # "12:34"
        if key not in buckets:
            buckets[key] = {"ts": label, "info": 0, "warning": 0, "critical": 0}
        sev = t.get("severity", "info")
        buckets[key][sev] = buckets[key].get(sev, 0) + 1
    sorted_buckets = sorted(buckets.items())         # sort by ISO key → chronological
    return [v for _, v in sorted_buckets[-12:]]


async def _run_scan() -> dict:
    """Run a detect → diagnose → heal pass via the healing scan service."""
    try:
        return await run_self_healing_scan()
    except Exception as exc:
        err = str(exc)
        print(f"[IRIS /scan] ERROR: {err}")
        push_activity(f"Scan error: {err[:120]}", "critical")
        return {"status": "error", "error": err}


async def _scheduled_pattern_scan():
    """Background task: run a pattern scan every pattern_window_minutes minutes."""
    await asyncio.sleep(60)
    while True:
        await asyncio.sleep(settings.pattern_window_minutes * 60)
        push_activity("Scanner: scheduled pattern scan starting", "adk")
        try:
            await _run_scan()
        except Exception as exc:
            push_activity(f"Scheduled scan error: {str(exc)[:120]}", "critical")
            print(f"[IRIS] Scheduled scan failed: {exc}")
