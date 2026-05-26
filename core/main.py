"""
IRIS FastAPI application.
Exposes:
  POST /event          — submit an IrisEvent for evaluation
  GET  /stream/alerts  — SSE stream of alerts to dashboard
  GET  /status         — shift stats for dashboard
  GET  /traces         — recent trace feed for dashboard
  POST /scan           — trigger manual pattern scan
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
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

from openinference.instrumentation.google_adk import GoogleADKInstrumentor
from phoenix.otel import register

from core.agents.orchestrator import iris_orchestrator
from core.agents.tools.eval_tools import (
    push_dashboard_alert,
    run_allergy_contraindication_evaluation,
    run_attribution_evaluation,
    run_context_gap_evaluation,
    run_dosage_boundary_evaluation,
    run_drug_interaction_evaluation,
    run_factual_hallucination_evaluation,
    run_surgical_phase_evaluation,
    write_phoenix_span_annotation,
)
from core.config import settings
from core.state import alert_bus, healing_candidates, healing_history, recent_traces, self_heal_bus, shift_stats
from sdk.models import IrisEvent

os.environ["GOOGLE_API_KEY"] = settings.google_api_key
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "FALSE"
os.environ["PHOENIX_API_KEY"] = settings.phoenix_api_key
os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = settings.phoenix_client_url.rstrip("/")

# ── Suppress OTel context-detach noise ───────────────────────────────────────
# OTel catches the ValueError internally and logs it; the exception never propagates.
# The filter targets only "Failed to detach context" — all other OTel errors surface.
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
    All 7 evaluators run concurrently via asyncio.gather — each makes its own
    Gemini call independently. Alert dispatch and Phoenix annotations also run
    in parallel after evaluation completes.
    """
    event_json = event.model_dump_json()
    try:
        # All evaluators run concurrently — no sequential LLM routing overhead
        raw = await asyncio.gather(
            run_factual_hallucination_evaluation(event_json),
            run_context_gap_evaluation(event_json),
            run_dosage_boundary_evaluation(event_json),
            run_attribution_evaluation(event_json),
            run_surgical_phase_evaluation(event_json),
            run_drug_interaction_evaluation(event_json),
            run_allergy_contraindication_evaluation(event_json),
            return_exceptions=True,
        )

        evaluations = [
            r for r in raw
            if isinstance(r, dict) and not r.get("skipped") and not r.get("error")
        ]

        # Derive final severity from evaluation results
        sevs = [e.get("severity", "info") for e in evaluations]
        if "critical" in sevs:
            final_severity = "critical"
        elif "warning" in sevs:
            final_severity = "warning"
        else:
            final_severity = "info"

        # Shift counters
        shift_stats["total_traces"] += 1
        if final_severity in ("warning", "critical"):
            shift_stats["hallucinations_caught"] = shift_stats.get("hallucinations_caught", 0) + 1

        low_confidence = [
            e for e in evaluations
            if (e.get("confidence") or 1.0) < 0.6
        ]
        if low_confidence:
            shift_stats["human_escalations"] = shift_stats.get("human_escalations", 0) + 1

        # Worst-scoring evaluator drives the alert description
        worst = min(evaluations, key=lambda e: e.get("score", 10.0), default=None)
        failure_type = worst["evaluator"] if worst else "none"
        description = (
            worst.get("rationale", "")[:200]
            if worst and final_severity != "info"
            else "All safety checks passed"
        )

        # Alert dispatch + all Phoenix annotations in parallel
        await asyncio.gather(
            push_dashboard_alert(
                severity=final_severity,
                agent_name=event.agent_name,
                trace_id=event.trace_id,
                query_type=str(event.query_type),
                failure_type=failure_type,
                description=description,
                eval_score=worst.get("score", 10.0) if worst else 10.0,
            ),
            *[
                write_phoenix_span_annotation(
                    trace_id=event.trace_id,
                    agent_name=event.agent_name,
                    query_type=str(event.query_type),
                    evaluator_name=e["evaluator"],
                    score=float(e.get("score", 5.0)),
                    severity=e.get("severity", "info"),
                    rationale=e.get("rationale", ""),
                    passed=bool(e.get("passed", True)),
                )
                for e in evaluations
            ],
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
            "retrieved_context": event.retrieved_context.model_dump(),
            "latency_ms": event.latency_ms,
            "evaluations": evaluations,
        })

        return {
            "trace_id": event.trace_id,
            "status": "evaluated",
            "severity": final_severity,
            "result": json.dumps({"evaluations": evaluations, "final_severity": final_severity}),
        }

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/scan")
async def trigger_pattern_scan() -> dict:
    """Manually trigger a pattern detection scan."""
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
            if adk_event.is_final_response() and adk_event.content:
                for part in adk_event.content.parts:
                    if part.text:
                        result_text = part.text
        return {"status": "scan_complete", "result": result_text}
    except Exception as exc:
        err = str(exc)
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
    """List prompt mutation candidates pending human approval."""
    return {
        "candidates": [c.model_dump(mode="json") for c in healing_candidates],
        "count": len(healing_candidates),
    }


@app.post("/healing/approve/{candidate_id}")
async def approve_healing_candidate(candidate_id: str) -> dict:
    """Approve a healing candidate — deploys the new prompt to Phoenix."""
    from core.healing.pipeline import approve_candidate
    candidate = await approve_candidate(candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail=f"Candidate {candidate_id} not found")
    return {"candidate_id": candidate_id, "status": candidate.status, "deployed_at": str(candidate.deployed_at)}


@app.post("/healing/reject/{candidate_id}")
async def reject_healing_candidate(candidate_id: str, reason: str = "") -> dict:
    """Reject a healing candidate — discards it and logs to history."""
    from core.healing.pipeline import reject_candidate
    candidate = await reject_candidate(candidate_id, reason)
    if candidate is None:
        raise HTTPException(status_code=404, detail=f"Candidate {candidate_id} not found")
    return {"candidate_id": candidate_id, "status": candidate.status}


@app.get("/healing/history")
async def healing_history_feed(limit: int = 50) -> dict:
    """Past healing candidates with before/after scores."""
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
    evaluator_stats = {
        e: {
            "runs": s["runs"],
            "failures": s["failures"],
            "skipped": s["skipped"],
            "avg_score": round(s["score_sum"] / s["runs"], 2) if s["runs"] else None,
            "critical_count": s["critical_count"],
        }
        for e, s in stats.items()
    }
    return {
        "evaluator_stats": evaluator_stats,
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
        chunk = ordered_traces[i : i + size]
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
    """
    Extract structured data from the orchestrator's text output.
    Handles markdown code blocks (```json ... ```) that Gemini often emits.
    Derives final_severity from the evaluations list when not explicitly set.
    """
    if not result_text:
        return {"final_severity": "info", "evaluations": []}

    # Strip markdown code fences
    clean = re.sub(r"```(?:json)?\s*", "", result_text)
    clean = re.sub(r"```\s*", "", clean).strip()

    # Find the first complete JSON object
    try:
        # Try the whole string first
        data = json.loads(clean)
    except json.JSONDecodeError:
        # Find the outermost {...} block
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

    # Extract or derive final_severity
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
    await asyncio.sleep(60)  # warm-up delay
    while True:
        await asyncio.sleep(settings.pattern_window_minutes * 60)
        try:
            message = types.Content(
                role="user",
                parts=[types.Part(text="SCAN_PATTERNS")],
            )
            async for _ in _runner.run_async(
                user_id=SYSTEM_USER_ID,
                session_id=SHIFT_SESSION_ID,
                new_message=message,
            ):
                pass
        except Exception as exc:
            print(f"[IRIS] Scheduled scan failed: {exc}")
