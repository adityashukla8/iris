"""
Deterministic alert dispatch — replaces the former LLM alert_dispatcher agent.

Severity routing is fixed policy, not a judgment call, so it does not need an LLM:
  info     → dashboard live feed
  warning  → dashboard yellow badge
  critical → dashboard red badge + flagged for human review

Event-driven scan trigger (tier 1):
  After dispatching a CRITICAL alert, IRIS checks whether the failure count for
  this (agent, prompt_hash, query_type) has crossed the autonomous trigger threshold.
  If yes — and no scan is currently running and no cooldown is active — a background
  scan is fired immediately without waiting for the next scheduled slot.
"""
from __future__ import annotations

import asyncio
import time

from core.config import settings
from core.evaluators.service import EvaluationOutcome
from core.state import (
    alert_bus,
    is_cluster_in_cooldown,
    last_scan_time,
    push_activity,
    recent_traces,
    scan_lock,
)
import core.state as _state
from sdk.models import AlertEvent, IrisEvent, Severity


def _worst_result(outcome: EvaluationOutcome):
    failing = [r for r in outcome.results if not r.passed]
    if not failing:
        return None
    return min(failing, key=lambda r: r.score)


def dispatch_alert(event: IrisEvent, outcome: EvaluationOutcome) -> AlertEvent | None:
    """Push a dashboard alert reflecting the worst evaluator finding."""
    worst = _worst_result(outcome)
    if worst is None:
        # All clear — info-level visibility only.
        alert = AlertEvent(
            severity=Severity.INFO,
            agent_name=event.agent_name,
            trace_id=event.trace_id,
            query_type=str(event.query_type),
            failure_type="none",
            description=f"{event.agent_name} {event.query_type}: all safety checks passed.",
            eval_score=max((r.score for r in outcome.results), default=10.0),
        )
    else:
        sev = worst.severity
        if sev is Severity.CRITICAL:
            desc = (
                f"IRIS: {worst.evaluator} detected in {event.agent_name} "
                f"{event.query_type}. Human review required."
            )
        else:
            desc = f"{worst.evaluator} flagged {event.agent_name} {event.query_type}: {worst.rationale[:160]}"
        alert = AlertEvent(
            severity=sev,
            agent_name=event.agent_name,
            trace_id=event.trace_id,
            query_type=str(event.query_type),
            failure_type=worst.evaluator,
            description=desc[:300],
            eval_score=worst.score,
        )

    try:
        alert_bus.put_nowait(alert)
    except Exception:
        pass

    level = "critical" if alert.severity is Severity.CRITICAL else "warn" if alert.severity is Severity.WARNING else "info"
    push_activity(f"Alert dispatched — {alert.severity.value}: {alert.failure_type}", level)

    # Event-driven trigger: fire an autonomous background scan when a CRITICAL failure
    # cluster crosses the threshold, rather than waiting for the 30-minute scheduler.
    if alert.severity is Severity.CRITICAL:
        _maybe_trigger_scan(event)

    return alert


def _maybe_trigger_scan(event: IrisEvent) -> None:
    """Check whether this CRITICAL event pushes a cluster past the autonomous scan threshold.

    Conditions required (all must hold):
    1. Failure count for (agent, prompt_hash, query_type) >= pattern_min_samples × event_trigger_multiplier
    2. No scan is currently running (scan_lock.locked() is False)
    3. Cluster is not in cooldown (recently healed)
    4. A scan did not just run (scan_debounce_seconds has elapsed since last_scan_time)
    """
    from core.healing.prompt_identity import prompt_hash as compute_hash
    phash = compute_hash(event.system_prompt)
    agent = event.agent_name
    qt = str(event.query_type)

    # Count critical/warning failures for this specific (agent, prompt, query_type) cluster
    threshold = settings.pattern_min_samples * settings.event_trigger_multiplier
    cluster_failures = sum(
        1 for t in recent_traces
        if (t.get("agent_name") == agent
            and t.get("prompt_hash") == phash
            and t.get("query_type") == qt
            and t.get("severity") in ("critical", "warning"))
    )
    if cluster_failures < threshold:
        return

    # Debounce: don't re-trigger if a scan just ran
    if time.monotonic() - _state.last_scan_time < settings.scan_debounce_seconds:
        return

    # Lock: don't trigger if one is already in flight
    if scan_lock.locked():
        return

    # Cooldown: don't re-heal the same cluster if it was just healed
    cooldown_secs = settings.heal_cooldown_minutes * 60
    if is_cluster_in_cooldown(agent, phash, qt, cooldown_secs):
        return

    push_activity(
        f"Scanner: {agent} {qt} has {cluster_failures} critical failures "
        f"(threshold={threshold}) — triggering autonomous scan",
        "critical",
    )
    print(f"[Scanner] event-driven trigger: {agent}|{phash[:6]}|{qt} ({cluster_failures} failures)")

    # Import here to avoid circular import at module load time
    from core.healing.scan import run_self_healing_scan
    asyncio.create_task(run_self_healing_scan())
