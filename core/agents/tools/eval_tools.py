"""
ADK function tools wrapping IRIS EvalPlugins.
Each function takes the serialized IrisEvent JSON and returns a dict.
The Safety Evaluator LlmAgent calls these tools.
"""
from __future__ import annotations

from sdk.models import IrisEvent
from core.evaluators.dosage_boundary import DosageBoundaryEvaluator
from core.evaluators.factual_hallucination import FactualHallucinationEvaluator
from core.evaluators.attribution import AttributionEvaluator
from core.evaluators.context_gap import ContextGapEvaluator
from core.evaluators.surgical_phase import SurgicalPhaseEvaluator
from core.evaluators.drug_interaction import DrugInteractionEvaluator
from core.evaluators.allergy_contraindication import AllergyContraindicationEvaluator

_dosage_evaluator = DosageBoundaryEvaluator()
_hallucination_evaluator = FactualHallucinationEvaluator()
_attribution_evaluator = AttributionEvaluator()
_context_gap_evaluator = ContextGapEvaluator()
_surgical_phase_evaluator = SurgicalPhaseEvaluator()
_drug_interaction_evaluator = DrugInteractionEvaluator()
_allergy_contraindication_evaluator = AllergyContraindicationEvaluator()


async def run_dosage_boundary_evaluation(event_json: str) -> dict:
    """
    Evaluate whether drug doses stated in the clinical AI output are within
    FDA-approved ranges for this specific patient (renal function, weight, allergies).
    Returns a dict with: evaluator, score (0-10), severity, passed, rationale, flagged_claims.
    """
    try:
        event = IrisEvent.model_validate_json(event_json)
        result = await _dosage_evaluator.evaluate(event)
        if result is None:
            return {"evaluator": "dosage_boundary", "skipped": True, "reason": "Not applicable for this query type"}
        return result.model_dump()
    except Exception as exc:
        return {"evaluator": "dosage_boundary", "error": str(exc), "score": 5.0, "severity": "warning"}


async def run_factual_hallucination_evaluation(event_json: str) -> dict:
    """
    Evaluate whether drug names, procedure names, and lab values in the output
    are factually correct and exist in RxNorm/SNOMED. Flags misspellings,
    invented drug names, or physiologically impossible values.
    Returns a dict with: evaluator, score (0-10), severity, passed, rationale, flagged_claims.
    """
    try:
        event = IrisEvent.model_validate_json(event_json)
        result = await _hallucination_evaluator.evaluate(event)
        if result is None:
            return {"evaluator": "factual_hallucination", "skipped": True, "reason": "Not applicable"}
        return result.model_dump()
    except Exception as exc:
        return {"evaluator": "factual_hallucination", "error": str(exc), "score": 5.0, "severity": "warning"}


async def run_attribution_evaluation(event_json: str) -> dict:
    """
    Evaluate whether every factual claim in the output is correctly attributed
    to the patient identified in the retrieved context. Catches cross-patient
    data contamination — a critical OR safety risk.
    Returns a dict with: evaluator, score (0-10), severity, passed, rationale, flagged_claims.
    """
    try:
        event = IrisEvent.model_validate_json(event_json)
        result = await _attribution_evaluator.evaluate(event)
        if result is None:
            return {"evaluator": "attribution", "skipped": True, "reason": "Not applicable"}
        return result.model_dump()
    except Exception as exc:
        return {"evaluator": "attribution", "error": str(exc), "score": 5.0, "severity": "warning"}


async def run_context_gap_evaluation(event_json: str) -> dict:
    """
    Evaluate whether the agent answered a clinical question while missing
    key patient variables in its retrieved context (e.g., dosage recommendation
    without creatinine clearance). This catches retrieval failures, not hallucinations.
    Returns a dict with: evaluator, score (0-10), severity, passed, rationale, flagged_claims.
    """
    try:
        event = IrisEvent.model_validate_json(event_json)
        result = await _context_gap_evaluator.evaluate(event)
        if result is None:
            return {"evaluator": "context_gap", "skipped": True, "reason": "Not applicable"}
        return result.model_dump()
    except Exception as exc:
        return {"evaluator": "context_gap", "error": str(exc), "score": 5.0, "severity": "warning"}


async def run_surgical_phase_evaluation(event_json: str) -> dict:
    """
    Evaluate whether the agent output is clinically appropriate for the current
    surgical phase (pre-op, induction, incision, dissection, closure, post-op).
    Skipped automatically when no surgical_phase is present in the event.
    Returns a dict with: evaluator, score (0-10), severity, passed, rationale, flagged_claims.
    """
    try:
        event = IrisEvent.model_validate_json(event_json)
        result = await _surgical_phase_evaluator.evaluate(event)
        if result is None:
            return {"evaluator": "surgical_phase", "skipped": True, "reason": "No surgical_phase in event"}
        return result.model_dump()
    except Exception as exc:
        return {"evaluator": "surgical_phase", "error": str(exc), "score": 5.0, "severity": "warning"}


async def run_drug_interaction_evaluation(event_json: str) -> dict:
    """
    Evaluate whether the agent's recommended drugs interact dangerously with the
    patient's current medications. Polypharmacy is the #1 ICU medication error.
    Checks all (recommended × current) pairs for severe/moderate DDIs using Gemini.
    Returns a dict with: evaluator, score (0-10), severity, passed, rationale,
    flagged_claims, reasoning_chain, confidence.
    """
    try:
        event = IrisEvent.model_validate_json(event_json)
        result = await _drug_interaction_evaluator.evaluate(event)
        if result is None:
            return {"evaluator": "drug_interaction", "skipped": True, "reason": "Not applicable"}
        return result.model_dump()
    except Exception as exc:
        return {"evaluator": "drug_interaction", "error": str(exc), "score": 5.0, "severity": "warning"}


async def run_allergy_contraindication_evaluation(event_json: str) -> dict:
    """
    Evaluate whether the agent recommends a drug the patient is allergic to,
    including cross-reactive drug families (penicillin→cephalosporins, sulfonamides→sulfonylureas,
    NSAIDs→aspirin, etc.). Life-safety critical — anaphylaxis is preventable.
    Returns a dict with: evaluator, score (0-10), severity, passed, rationale,
    flagged_claims, reasoning_chain, confidence.
    """
    try:
        event = IrisEvent.model_validate_json(event_json)
        result = await _allergy_contraindication_evaluator.evaluate(event)
        if result is None:
            return {"evaluator": "allergy_contraindication", "skipped": True, "reason": "Not applicable"}
        return result.model_dump()
    except Exception as exc:
        return {"evaluator": "allergy_contraindication", "error": str(exc), "score": 5.0, "severity": "warning"}


async def run_healing_pipeline_tool(diagnosis_json: str) -> dict:
    """
    Trigger the Python healing pipeline from a HealingDiagnosis JSON produced by
    the self_healer MCP agent. This is the bridge between the MCP read path
    (pattern_detector → self_healer → Phoenix spans/prompts/datasets) and the
    Python write path (TextGrad mutation → counterfactual validation → Phoenix deploy).

    Call this immediately after self_healer returns its HealingDiagnosis JSON.
    Runs the pipeline as a background task and returns immediately.

    diagnosis_json: the complete HealingDiagnosis JSON string from self_healer output.
    """
    import asyncio
    import json
    import re
    from core.healing.models import HealingDiagnosis
    from core.healing.pipeline import run_healing_pipeline

    # Strip markdown code fences if Gemini wrapped the JSON
    clean = re.sub(r"```(?:json)?\s*", "", diagnosis_json)
    clean = re.sub(r"```\s*", "", clean).strip()
    start = clean.find("{")
    if start != -1:
        clean = clean[start:]

    try:
        diagnosis = HealingDiagnosis.model_validate_json(clean)
        asyncio.create_task(run_healing_pipeline(diagnosis))
        return {
            "triggered": True,
            "candidate_id": diagnosis.candidate_id,
            "query_type": diagnosis.query_type,
            "agent_name": diagnosis.agent_name,
            "hallucination_rate": diagnosis.hallucination_rate,
            "message": "Pipeline started: TextGrad mutation → counterfactual validation → Phoenix prompt deploy",
        }
    except Exception as exc:
        return {"triggered": False, "error": str(exc)}


async def write_phoenix_span_annotation(
    trace_id: str,
    agent_name: str,
    query_type: str,
    evaluator_name: str,
    score: float,
    severity: str,
    rationale: str,
    passed: bool,
) -> dict:
    """
    Write a safety evaluation result as a Phoenix span annotation via the REST API.
    Called after each evaluation to record the result in Arize Phoenix for observability.
    Returns {"success": true/false}.
    """
    from core.phoenix.client import phoenix_client
    from sdk.models import EvalResult, IrisEvent, Severity

    mock_event = IrisEvent(
        agent_name=agent_name,
        trace_id=trace_id,
        query_type=query_type,
        input_prompt="",
        output_text="",
    )
    result = EvalResult(
        evaluator=evaluator_name,
        score=score,
        severity=Severity(severity),
        passed=passed,
        rationale=rationale,
    )
    success = await phoenix_client.annotate_span(mock_event, result)
    return {"success": success}


async def push_dashboard_alert(
    severity: str,
    agent_name: str,
    trace_id: str,
    query_type: str,
    failure_type: str,
    description: str,
    eval_score: float,
) -> dict:
    """
    Push a safety alert to the IRIS dashboard live feed via the internal event bus.
    severity must be one of: info, warning, critical.
    Returns {"dispatched": true}.
    """
    from sdk.models import AlertEvent, Severity
    from core.state import alert_bus

    alert = AlertEvent(
        severity=Severity(severity),
        agent_name=agent_name,
        trace_id=trace_id,
        query_type=query_type,
        failure_type=failure_type,
        description=description[:300],
        eval_score=eval_score,
    )
    try:
        alert_bus.put_nowait(alert)
        return {"dispatched": True}
    except Exception:
        return {"dispatched": False}
