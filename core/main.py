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
import logging
import os
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from openinference.instrumentation.google_adk import GoogleADKInstrumentor
from phoenix.otel import register

from core.agents.orchestrator import iris_orchestrator
from core.config import settings
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

os.environ["GOOGLE_API_KEY"] = settings.google_api_key
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "FALSE"
os.environ["PHOENIX_API_KEY"] = settings.phoenix_api_key
os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = settings.phoenix_client_url.rstrip("/")

# ── Suppress OTel context-detach noise ───────────────────────────────────────
class _SuppressDetachNoise(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "Failed to detach context" not in record.getMessage()

logging.getLogger("opentelemetry.context").addFilter(_SuppressDetachNoise())
# ─────────────────────────────────────────────────────────────────────────────

_tracer_provider = register(
    project_name="iris-clinical",
    batch=True,
    set_global_tracer_provider=False,
    auto_instrument=True,
    verbose=False,
)
GoogleADKInstrumentor().instrument(tracer_provider=_tracer_provider)

_session_service = InMemorySessionService()
_runner = Runner(
    agent=iris_orchestrator,
    app_name="iris-clinical",
    session_service=_session_service,
)

SHIFT_SESSION_ID = "shift-001"
SYSTEM_USER_ID = "iris-system"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _session_service.create_session(
        app_name="iris-clinical",
        user_id=SYSTEM_USER_ID,
        session_id=SHIFT_SESSION_ID,
    )
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
    Receive an IrisEvent from a connected clinical AI agent.
    Runs the full IRIS evaluation pipeline via the ADK orchestrator.
    """
    event_json = event.model_dump_json()
    push_activity(f"Event received — {event.agent_name} · {event.query_type}", "info")
    message = types.Content(
        role="user",
        parts=[types.Part(text=f"IrisEvent:\n{event_json}")],
    )

    result_text = ""
    try:
        async for adk_event in _runner.run_async(
            user_id=SYSTEM_USER_ID,
            session_id=SHIFT_SESSION_ID,
            new_message=message,
        ):
            _handle_adk_event(adk_event)
            if adk_event.is_final_response() and adk_event.content:
                for part in adk_event.content.parts:
                    if part.text:
                        result_text = part.text
                        break

        shift_stats["total_traces"] += 1

        parsed = _parse_result(result_text)
        final_severity = parsed.get("final_severity", "info")
        evaluations = parsed.get("evaluations", [])

        if final_severity in ("warning", "critical"):
            shift_stats["hallucinations_caught"] = shift_stats.get("hallucinations_caught", 0) + 1

        low_confidence = [
            e for e in evaluations
            if (e.get("confidence") or 1.0) < 0.6 and not e.get("skipped")
        ]
        if low_confidence:
            shift_stats["human_escalations"] = shift_stats.get("human_escalations", 0) + 1

        level = "critical" if final_severity == "critical" else "warn" if final_severity == "warning" else "info"
        push_activity(
            f"Evaluation complete — {len(evaluations)} evaluators · severity: {final_severity}",
            level,
        )

        recent_traces.appendleft({
            "trace_id": event.trace_id,
            "timestamp": event.timestamp.isoformat(),
            "agent_name": event.agent_name,
            "agent_version": event.agent_version,
            "query_type": str(event.query_type),
            "severity": final_severity,
            "input_prompt": event.input_prompt,
            "output_text": event.output_text,
            "retrieved_context": event.retrieved_context.model_dump() if event.retrieved_context else {},
            "latency_ms": event.latency_ms,
            "evaluations": evaluations,
        })

        return {
            "trace_id": event.trace_id,
            "status": "evaluated",
            "severity": final_severity,
            "result": result_text,
        }

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/scan")
async def trigger_pattern_scan() -> dict:
    """Manually trigger a pattern detection scan."""
    push_activity("ADK: iris_orchestrator invoked — SCAN_PATTERNS", "adk")
    message = types.Content(
        role="user",
        parts=[types.Part(text="SCAN_PATTERNS")],
    )
    result_text = ""
    try:
        async for adk_event in _runner.run_async(
            user_id=SYSTEM_USER_ID,
            session_id=SHIFT_SESSION_ID,
            new_message=message,
        ):
            _handle_adk_event(adk_event)
            if adk_event.is_final_response() and adk_event.content:
                for part in adk_event.content.parts:
                    if part.text:
                        result_text = part.text
        _push_scan_activity(result_text)
        return {"status": "scan_complete", "result": result_text}
    except Exception as exc:
        err = str(exc)
        push_activity(f"Scan error: {err[:120]}", "critical")
        return {"status": "error", "error": err}


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

_last_event_author: str = ""


def _handle_adk_event(event) -> None:
    """
    Parse mid-stream ADK Events to emit activity log lines.
    Extracts agent transitions, tool calls, and tool responses from the
    native ADK event stream — no separate callbacks needed.
    """
    global _last_event_author

    author = getattr(event, "author", None) or ""
    if author and author != "user" and author != _last_event_author:
        push_activity(f"ADK: agent active — {author}", "adk")
        _last_event_author = author

    content = getattr(event, "content", None)
    if not content:
        return

    for part in content.parts or []:
        fc = getattr(part, "function_call", None)
        if fc and fc.name:
            args_preview = _trim(dict(fc.args or {}), 80)
            push_activity(f"Tool call → {fc.name}({args_preview})", "mcp")

        fr = getattr(part, "function_response", None)
        if fr and fr.name:
            resp_preview = _trim(fr.response or {}, 100)
            push_activity(f"Tool result ← {fr.name}: {resp_preview}", "mcp")


def _trim(obj, max_len: int) -> str:
    s = json.dumps(obj) if not isinstance(obj, str) else obj
    return s[:max_len] + "…" if len(s) > max_len else s


def _push_scan_activity(result_text: str) -> None:
    """Parse a scan result JSON and emit human-readable activity events."""
    if not result_text:
        push_activity("Scan returned no output", "warn")
        return
    try:
        clean = re.sub(r"```(?:json)?\s*", "", result_text)
        clean = re.sub(r"```\s*", "", clean).strip()
        start = clean.find("{")
        end = clean.rfind("}")
        data = json.loads(clean[start:end + 1]) if start != -1 else {}
    except Exception:
        data = {}

    if data.get("clusters_analyzed") is not None:
        push_activity(
            f"Pattern scan: {data['clusters_analyzed']} cluster(s) analyzed",
            "adk",
        )
    clusters = data.get("failure_clusters") or []
    if not clusters:
        push_activity("No failure clusters detected — system healthy", "heal")
    for c in clusters:
        rate = int((c.get("hallucination_rate") or 0) * 100)
        push_activity(
            f"FAILURE CLUSTER: {c.get('query_type', '?')} — {rate}% failure rate"
            f" ({c.get('span_count', '?')} spans, worst score {c.get('worst_score', '?')})",
            "critical",
        )
    if data.get("healing_required"):
        push_activity("ADK: self_healer invoked — DIAGNOSE phase", "adk")
        push_activity(
            "MCP: get-latest-prompt · add-dataset-examples · get-dataset-examples",
            "mcp",
        )


_EVAL_NAMES = [
    "dosage_boundary", "factual_hallucination", "drug_interaction",
    "allergy_contraindication", "attribution", "context_gap", "surgical_phase",
]


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
        "severity_timeline": _bucket_traces(list(reversed(traces)), 12),
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


def _bucket_traces(ordered_traces: list[dict], buckets: int) -> list[dict]:
    if not ordered_traces:
        return []
    n = len(ordered_traces)
    size = max(1, n // buckets)
    result = []
    for i in range(0, n, size):
        chunk = ordered_traces[i: i + size]
        info = sum(1 for t in chunk if t.get("severity", "info") == "info")
        warn = sum(1 for t in chunk if t.get("severity") == "warning")
        crit = sum(1 for t in chunk if t.get("severity") == "critical")
        ts = chunk[0].get("timestamp", "")
        result.append({
            "ts": ts[11:16] if len(ts) > 15 else ts,
            "info": info,
            "warning": warn,
            "critical": crit,
        })
    return result[-12:]


def _parse_result(result_text: str) -> dict:
    if not result_text:
        return {"final_severity": "info", "evaluations": []}

    clean = re.sub(r"```(?:json)?\s*", "", result_text)
    clean = re.sub(r"```\s*", "", clean).strip()

    try:
        data = json.loads(clean)
    except json.JSONDecodeError:
        start = clean.find("{")
        if start == -1:
            return {"final_severity": "info", "evaluations": []}
        depth = 0
        end = start
        for i, ch in enumerate(clean[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        try:
            data = json.loads(clean[start:end])
        except json.JSONDecodeError:
            return {"final_severity": "info", "evaluations": []}

    severity = data.get("final_severity") or data.get("worst_severity")
    if not severity:
        evals = data.get("evaluations", [])
        sevs = [e.get("severity", "info") for e in evals if not e.get("skipped")]
        if "critical" in sevs:
            severity = "critical"
        elif "warning" in sevs:
            severity = "warning"
        else:
            severity = "info"

    data["final_severity"] = severity
    return data


async def _scheduled_pattern_scan():
    """Background task: scan for patterns every N minutes via ADK orchestrator."""
    await asyncio.sleep(60)
    while True:
        await asyncio.sleep(settings.pattern_window_minutes * 60)
        push_activity("ADK: scheduled SCAN_PATTERNS — iris_orchestrator invoked", "adk")
        result_text = ""
        try:
            message = types.Content(
                role="user",
                parts=[types.Part(text="SCAN_PATTERNS")],
            )
            async for adk_event in _runner.run_async(
                user_id=SYSTEM_USER_ID,
                session_id=SHIFT_SESSION_ID,
                new_message=message,
            ):
                _handle_adk_event(adk_event)
                if adk_event.is_final_response() and adk_event.content:
                    for part in adk_event.content.parts:
                        if part.text:
                            result_text = part.text
            _push_scan_activity(result_text)
        except Exception as exc:
            push_activity(f"Scheduled scan error: {str(exc)[:120]}", "critical")
            print(f"[IRIS] Scheduled scan failed: {exc}")
