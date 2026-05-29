"""
Self-healing scan orchestration — deterministic Python service.

Replaces the custom IrisScanAgent (a BaseAgent._run_async_impl, which ADK 2.0's
workflow runtime bypasses). Only the pattern detector is a genuine agent (it uses
the Phoenix MCP server to introspect IRIS's own traces at runtime — the Arize
requirement). Everything after detection is deterministic compute, so it is a plain
async pipeline rather than a forced LLM workflow:

  pattern_detector (ADK + MCP)  →  for each failure cluster:
      fetch REAL failing examples from live traces
      diagnose (root cause + log dataset)
      run healing pipeline (mutate → validate → gate → deploy)
"""
from __future__ import annotations

import json
import re
import uuid

from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from core.agents.pattern_detector import pattern_detector_agent
from core.config import settings
from core.healing.diagnose import diagnose_cluster
from core.healing.pipeline import run_healing_pipeline
from core.state import push_activity, recent_traces

_SCAN_USER_ID = "iris-scanner"
_session_service = InMemorySessionService()
_runner = Runner(
    agent=pattern_detector_agent,
    app_name="iris-scan",
    session_service=_session_service,
)


async def run_self_healing_scan() -> dict:
    """Run a full detect → diagnose → heal pass. Returns the detection summary."""
    detected = await _detect_patterns()
    clusters = detected.get("failure_clusters") or []

    # Resilience: if the MCP/LLM detector produced nothing usable (e.g. a transient
    # MALFORMED_FUNCTION_CALL), fall back to deterministic clustering over the live
    # traces IRIS already holds — the heal loop must not depend on LLM tool-calling.
    if clusters:
        print(f"[Scanner] DETECTION SOURCE = phoenix-mcp (pattern_detector) — {len(clusters)} cluster(s)")
        push_activity(f"Scanner: detection via Phoenix MCP — {len(clusters)} cluster(s)", "adk")
    else:
        print("[Scanner] pattern_detector returned no clusters — trying deterministic fallback over live traces")
        push_activity("Scanner: MCP detector returned nothing — trying deterministic trace clustering", "warn")
        fallback = _detect_from_traces()
        fb_clusters = fallback.get("failure_clusters") or []
        if fb_clusters:
            print(f"[Scanner] DETECTION SOURCE = deterministic-fallback (recent_traces) — {len(fb_clusters)} cluster(s)")
            push_activity(
                f"Scanner: deterministic fallback found {len(fb_clusters)} cluster(s) from live traces",
                "warn",
            )
            detected = fallback
            clusters = fb_clusters
        else:
            print("[Scanner] deterministic fallback also found no failure clusters")
            push_activity("Scanner: deterministic fallback found no clusters either", "adk")

    push_activity(
        f"Scanner: {detected.get('clusters_analyzed', 0)} cluster(s) analyzed, "
        f"{len(clusters)} failure cluster(s)",
        "adk",
    )

    if not detected.get("healing_required") or not clusters:
        push_activity("Scanner: no failure clusters — system healthy", "heal")
        return {"status": "scan_complete", "healing_required": False, "result": json.dumps(detected)}

    for cluster in clusters:
        qt = cluster.get("query_type", "?")
        rate = int((cluster.get("hallucination_rate") or 0) * 100)
        push_activity(
            f"Scanner: FAILURE CLUSTER — {qt} {rate}% failure rate "
            f"(worst score {cluster.get('worst_score', '?')})",
            "critical",
        )
        examples = _fetch_failing_examples(cluster)
        if not examples:
            push_activity(f"Scanner: no live examples for {qt} — skipping heal", "warn")
            continue
        diagnosis = await diagnose_cluster(cluster, examples)
        await run_healing_pipeline(diagnosis)

    return {"status": "scan_complete", "healing_required": True, "result": json.dumps(detected)}


async def _detect_patterns() -> dict:
    session_id = f"scan-{uuid.uuid4().hex[:12]}"
    await _session_service.create_session(
        app_name="iris-scan", user_id=_SCAN_USER_ID, session_id=session_id
    )
    push_activity("Scanner: detecting failure patterns via Phoenix MCP", "adk")
    message = types.Content(role="user", parts=[types.Part(text="SCAN_PATTERNS")])

    try:
        async for event in _runner.run_async(
            user_id=_SCAN_USER_ID, session_id=session_id, new_message=message
        ):
            _push_mcp_activity(event)
            _log_malformed(event)
    except Exception as exc:
        print(f"[Scanner] pattern_detector run failed: {exc}")
        push_activity(f"Scanner: pattern_detector run error — {str(exc)[:100]}", "critical")
        return {}

    session = await _session_service.get_session(
        app_name="iris-scan", user_id=_SCAN_USER_ID, session_id=session_id
    )
    raw = session.state.get("detected_patterns", "") if session else ""
    if not raw:
        print("[Scanner] pattern_detector wrote no detected_patterns to session state")
    return _parse_json(raw) or {}


def _detect_from_traces() -> dict:
    """Deterministic failure clustering over IRIS's own in-memory traces (no LLM, no MCP).

    Groups by (agent_name, prompt_hash, query_type) so each cluster corresponds to a
    specific prompt version from a specific agent. This is what we heal — not a global
    query-type category, but a particular (agent, prompt) pair that is failing.
    """
    groups: dict[str, dict] = {}
    for t in recent_traces:
        agent = str(t.get("agent_name", "unknown"))
        phash = str(t.get("prompt_hash", "none"))
        qt = str(t.get("query_type", "general"))
        key = f"{agent}|{phash}|{qt}"
        worst = _worst_eval(t.get("evaluations", []))
        g = groups.setdefault(key, {
            "query_type": qt,
            "agent_name": agent,
            "prompt_hash": phash,
            "system_prompt": t.get("system_prompt", ""),
            "span_count": 0,
            "failure_count": 0,
            "worst_score": 10.0,
            "sample_trace_ids": [],
        })
        g["span_count"] += 1
        if t.get("severity") != "info":
            g["failure_count"] += 1
            if t.get("trace_id"):
                g["sample_trace_ids"].append(t["trace_id"])
        if worst is not None:
            g["worst_score"] = min(g["worst_score"], worst[0])
        # Keep the system_prompt populated from any trace in the group
        if not g["system_prompt"] and t.get("system_prompt"):
            g["system_prompt"] = t["system_prompt"]

    clusters = []
    for g in groups.values():
        rate = g["failure_count"] / g["span_count"] if g["span_count"] else 0.0
        g["hallucination_rate"] = round(rate, 3)
        g["sample_trace_ids"] = g["sample_trace_ids"][:5]
        if rate > settings.pattern_hallucination_threshold and g["span_count"] >= settings.pattern_min_samples:
            clusters.append(g)

    return {
        "clusters_analyzed": len(groups),
        "failure_clusters": clusters,
        "healing_required": bool(clusters),
        "source": "deterministic-fallback",
    }


def _log_malformed(event) -> None:
    fr = getattr(event, "finish_reason", None) or getattr(event, "error_code", None)
    if fr and "MALFORMED" in str(fr):
        author = getattr(event, "author", "?")
        print(f"[Scanner] MALFORMED_FUNCTION_CALL from {author} — MCP detection unusable, will fall back")
        push_activity(f"Scanner: {author} hit MALFORMED_FUNCTION_CALL — falling back", "critical")


def _fetch_failing_examples(cluster: dict) -> list[dict]:
    """Pull the worst-scoring REAL traces for this cluster's (agent, prompt_hash, query_type)."""
    query_type = cluster.get("query_type")
    agent_name = cluster.get("agent_name")
    phash = cluster.get("prompt_hash", "none")
    candidates = []
    for t in recent_traces:
        if str(t.get("query_type")) != str(query_type):
            continue
        if str(t.get("agent_name")) != str(agent_name):
            continue
        # Match prompt_hash when available; fall back to any trace for this agent+query_type
        # when prompt_hash was "none" (events sent without a system_prompt).
        if phash != "none" and str(t.get("prompt_hash", "none")) != phash:
            continue
        if t.get("severity") == "info":
            continue
        worst = _worst_eval(t.get("evaluations", []))
        if worst is None:
            continue
        score, violation = worst
        candidates.append({
            "input_prompt": t.get("input_prompt", ""),
            "output_text": t.get("output_text", ""),
            "system_prompt": t.get("system_prompt", ""),
            "prompt_hash": t.get("prompt_hash", "none"),
            "violation": violation,
            "score": score,
            "retrieved_context": t.get("retrieved_context", {}),
            "surgical_phase": t.get("surgical_phase"),
            "agent_name": t.get("agent_name", agent_name or "unknown"),
        })

    candidates.sort(key=lambda e: e["score"])
    return candidates[: settings.healing_validation_examples]


def _worst_eval(evaluations: list[dict]) -> tuple[float, str] | None:
    scored = [
        (float(e.get("score", 10.0)), e.get("rationale", "") or e.get("evaluator", ""))
        for e in evaluations
        if not e.get("skipped") and "score" in e
    ]
    if not scored:
        return None
    return min(scored, key=lambda x: x[0])


def _push_mcp_activity(event) -> None:
    content = getattr(event, "content", None)
    if not content:
        return
    for part in getattr(content, "parts", None) or []:
        fc = getattr(part, "function_call", None)
        if fc and fc.name:
            push_activity(f"MCP: {fc.name}({json.dumps(dict(fc.args or {}))[:80]})", "mcp")
        fr = getattr(part, "function_response", None)
        if fr and fr.name:
            push_activity(f"MCP result ← {fr.name}", "mcp")


def _parse_json(text: str) -> dict | None:
    if not text:
        return None
    clean = re.sub(r"```(?:json)?\s*|```", "", text).strip()
    start = clean.find("{")
    end = clean.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(clean[start : end + 1])
    except json.JSONDecodeError:
        return None
