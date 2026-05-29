"""
EvaluationService — deterministic fan-out over the IRIS evaluators.

Replaces the former LLM `safety_evaluator` router. Each evaluator self-reports
applicability (`is_applicable`) and returns None when it does not apply, so no LLM
is needed to decide which evaluators to run. Running this in plain Python removes a
whole class of MALFORMED_FUNCTION_CALL failures and is faster and cheaper.

Evaluators that need clinical judgment still call Gemini internally — the agentic
reasoning lives inside the evaluator, where it belongs.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from opentelemetry import trace as otel_trace

from core.evaluators.allergy_contraindication import AllergyContraindicationEvaluator
from core.evaluators.attribution import AttributionEvaluator
from core.evaluators.base import EvalPlugin
from core.evaluators.context_gap import ContextGapEvaluator
from core.evaluators.dosage_boundary import DosageBoundaryEvaluator
from core.evaluators.drug_interaction import DrugInteractionEvaluator
from core.evaluators.factual_hallucination import FactualHallucinationEvaluator
from core.evaluators.surgical_phase import SurgicalPhaseEvaluator
from core.phoenix.client import record_eval_on_span
from sdk.models import EvalResult, IrisEvent, Severity

# Registry — add an evaluator here and it is automatically run + traced + analysed.
EVALUATORS: list[EvalPlugin] = [
    FactualHallucinationEvaluator(),
    DosageBoundaryEvaluator(),
    AttributionEvaluator(),
    ContextGapEvaluator(),
    SurgicalPhaseEvaluator(),
    DrugInteractionEvaluator(),
    AllergyContraindicationEvaluator(),
]

EVALUATOR_NAMES: list[str] = [e.name for e in EVALUATORS]

_SEVERITY_RANK = {Severity.INFO: 0, Severity.WARNING: 1, Severity.CRITICAL: 2}


@dataclass
class EvaluationOutcome:
    results: list[EvalResult]
    worst_severity: Severity = Severity.INFO
    skipped: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)

    def to_feed_rows(self) -> list[dict]:
        """Rows for the dashboard trace feed / analytics (JSON-safe: enums → strings)."""
        rows = [r.model_dump(mode="json") for r in self.results]
        rows.extend({"evaluator": name, "skipped": True} for name in self.skipped)
        return rows


async def _run_one(evaluator: EvalPlugin, event: IrisEvent) -> EvalResult | None:
    try:
        return await evaluator.evaluate(event)
    except Exception as exc:
        print(f"[EvaluationService] {evaluator.name} raised: {exc}")
        return EvalResult.from_score(
            evaluator=evaluator.name,
            score=settings_warning_score(),
            rationale=f"Evaluator error: {str(exc)[:200]}",
            confidence=0.0,
        )


def settings_warning_score() -> float:
    from core.config import settings
    return settings.score_warning_threshold


async def evaluate_event(event: IrisEvent, span: otel_trace.Span | None = None) -> EvaluationOutcome:
    """
    Run every applicable evaluator concurrently, record results as span attributes,
    and return the aggregated outcome.
    """
    applicable = [e for e in EVALUATORS if e.is_applicable(event)]
    skipped = [e.name for e in EVALUATORS if e not in applicable]

    raw = await asyncio.gather(*(_run_one(e, event) for e in applicable))
    results = [r for r in raw if r is not None]
    # Evaluators that returned None at runtime count as skipped too.
    ran_names = {r.evaluator for r in results}
    skipped.extend(e.name for e in applicable if e.name not in ran_names)

    if span is not None:
        for r in results:
            record_eval_on_span(span, event, r)

    worst = Severity.INFO
    for r in results:
        if _SEVERITY_RANK[r.severity] > _SEVERITY_RANK[worst]:
            worst = r.severity
    if span is not None:
        span.set_attribute("iris.worst_severity", worst.value)

    return EvaluationOutcome(results=results, worst_severity=worst, skipped=skipped)
