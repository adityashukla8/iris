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
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime

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

# ── Python-level failure tracker ──────────────────────────────────────────────
# Tracks failures per (agent_name, query_type) independently of Phoenix MCP.
# Triggers healing when pattern_min_samples threshold is reached.
# The MCP-based self_healer agent is the deep path (reads Phoenix spans);
# this is the reliable fast path that works without Phoenix export latency.
_failure_buffer: dict[str, list[dict]] = defaultdict(list)
_healing_in_progress: set[str] = set()  # prevents duplicate healing runs
# ─────────────────────────────────────────────────────────────────────────────


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

templates = Jinja2Templates(directory="dashboard/templates")


@app.post("/event")
async def submit_event(event: IrisEvent) -> dict:
    """
    Receive an IrisEvent from a connected clinical AI agent.
    Runs the full IRIS evaluation pipeline via the ADK orchestrator.
    """
    event_json = event.model_dump_json()
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
            if adk_event.is_final_response() and adk_event.content:
                for part in adk_event.content.parts:
                    if part.text:
                        result_text = part.text
                        break

        shift_stats["total_traces"] += 1

        # Parse structured result from orchestrator output
        parsed = _parse_result(result_text)
        final_severity = parsed.get("final_severity", "info")
        evaluations = parsed.get("evaluations", [])

        # Update shift counters
        if final_severity in ("warning", "critical"):
            shift_stats["hallucinations_caught"] = shift_stats.get("hallucinations_caught", 0) + 1

        trace_summary = {
            "trace_id": event.trace_id,
            "timestamp": event.timestamp.isoformat(),
            "agent_name": event.agent_name,
            "query_type": str(event.query_type),
            "severity": final_severity,
            "evaluations": evaluations[:5],
        }
        recent_traces.appendleft(trace_summary)

        # Low-confidence escalation: evaluator is uncertain → flag for human review
        low_confidence = [e for e in evaluations if e.get("confidence", 1.0) < 0.6 and not e.get("skipped")]
        if low_confidence:
            shift_stats["human_escalations"] = shift_stats.get("human_escalations", 0) + 1

        # Python-level pattern tracking — triggers healing independently of MCP timing
        if final_severity in ("warning", "critical"):
            asyncio.create_task(
                _track_failure_and_maybe_heal(event, evaluations, final_severity)
            )

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
    message = types.Content(
        role="user",
        parts=[types.Part(text="SCAN_PATTERNS")],
    )
    result_text = ""
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


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "shift_stats": shift_stats,
    })


# ── Helpers ───────────────────────────────────────────────────────────────────

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


async def _track_failure_and_maybe_heal(
    event: IrisEvent,
    evaluations: list[dict],
    severity: str,
) -> None:
    """
    Python-level failure tracker. Accumulates failures per query_type and
    triggers the healing pipeline when pattern_min_samples threshold is reached.

    This runs in parallel with the MCP-based self_healer agent path.
    It doesn't depend on Phoenix export latency — it uses in-process data.
    """
    query_type = str(event.query_type)
    agent_name = event.agent_name

    # Collect per-evaluator flags for context
    flagged = []
    for ev in evaluations:
        if ev.get("severity") in ("warning", "critical") and not ev.get("skipped"):
            flagged.extend(ev.get("flagged_claims", []))
            flagged.append(ev.get("rationale", ""))

    entry = {
        "trace_id": event.trace_id,
        "agent_name": agent_name,
        "query_type": query_type,
        "severity": severity,
        "score": min((ev.get("score", 10) for ev in evaluations if not ev.get("skipped")), default=5),
        "output_text": event.output_text,
        "input_prompt": event.input_prompt,
        "violation": " | ".join(flagged)[:300],
        "timestamp": datetime.utcnow().isoformat(),
    }

    cluster_key = f"{agent_name}:{query_type}"
    _failure_buffer[cluster_key].append(entry)

    n_failures = len(_failure_buffer[cluster_key])
    print(f"[PatternTracker] {cluster_key}: {n_failures} failures tracked")

    if (
        n_failures >= settings.pattern_min_samples
        and cluster_key not in _healing_in_progress
    ):
        _healing_in_progress.add(cluster_key)
        print(f"[PatternTracker] Threshold reached for {cluster_key} — triggering healing pipeline")
        try:
            await _run_python_healing(cluster_key, agent_name, query_type)
        finally:
            # Reset after healing so subsequent failures can trigger a new cycle
            _failure_buffer[cluster_key].clear()
            _healing_in_progress.discard(cluster_key)


async def _run_python_healing(cluster_key: str, agent_name: str, query_type: str) -> None:
    """
    Build a HealingDiagnosis from the in-process failure buffer and run the
    Python healing pipeline (mutation → validation → gate/deploy).
    """
    from core.healing.models import HealingDiagnosis
    from core.healing.pipeline import run_healing_pipeline

    failures = _failure_buffer.get(cluster_key, [])
    if not failures:
        return

    n = len(failures)
    failure_rate = n / max(n, settings.pattern_min_samples)
    failing_span_ids = [f["trace_id"] for f in failures[:10]]

    # Summarise the dominant failure pattern for the mutation engine
    all_violations = " | ".join(f.get("violation", "") for f in failures if f.get("violation"))
    failure_analysis = (
        f"{n} consecutive {query_type} failures from {agent_name}. "
        f"Failure rate {failure_rate:.0%}. "
        f"Common violations: {all_violations[:300]}"
    )

    diagnosis = HealingDiagnosis(
        failure_cluster={
            "query_type": query_type,
            "agent_name": agent_name,
            "span_count": n,
            "hallucination_rate": failure_rate,
            "worst_score": min(f.get("score", 10) for f in failures),
            "sample_trace_ids": failing_span_ids[:3],
        },
        query_type=query_type,
        agent_name=agent_name,
        failing_span_ids=failing_span_ids,
        hallucination_rate=failure_rate,
        current_prompt_name=settings.healing_prompt_name,
        current_prompt_text="",   # mutation_engine uses fallback when empty
        dataset_name=f"iris-failures-{query_type}",
        examples_logged=0,
        failure_analysis=failure_analysis,
    )

    await run_healing_pipeline(diagnosis)


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
