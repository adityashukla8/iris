"""
Deterministic alert dispatch — replaces the former LLM alert_dispatcher agent.

Severity routing is fixed policy, not a judgment call, so it does not need an LLM:
  info     → dashboard live feed
  warning  → dashboard yellow badge
  critical → dashboard red badge + flagged for human review
"""
from __future__ import annotations

from core.evaluators.service import EvaluationOutcome
from core.state import alert_bus, push_activity
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
    return alert
