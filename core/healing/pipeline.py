"""
IRIS Self-Healing Pipeline — GENERATE → VALIDATE → GATE → DEPLOY.

Picks up from diagnose_cluster() with a HealingDiagnosis that carries REAL failing
examples (real input/output/violation pulled from live traces — no stubs):

  HealingDiagnosis
    → generate_candidate_prompt()   [GENERATE: TextGrad mutation on real examples]
    → validate_heal()               [VALIDATE: re-run IRIS evaluators on candidate]
    → gate (auto-approve or human queue)
    → deploy (new Phoenix prompt version, tagged production)
"""
from __future__ import annotations

from datetime import datetime

from core.config import settings
from core.healing.experiment import validate_heal
from core.healing.models import HealingCandidate, HealingDiagnosis
from core.healing.mutation_engine import generate_candidate_prompt
from core.healing.prompt_manager import prompt_manager
from core.state import healing_candidates, healing_history, push_activity, shift_stats


async def run_healing_pipeline(diagnosis: HealingDiagnosis) -> HealingCandidate | None:
    push_activity(
        f"HealingPipeline: starting for {diagnosis.query_type} "
        f"({diagnosis.hallucination_rate:.0%} failure rate)",
        "heal",
    )

    examples = diagnosis.failing_examples
    if not examples:
        push_activity("HealingPipeline: no failing examples — aborting", "warn")
        return None

    effective_prompt = diagnosis.current_prompt_text or settings.healing_seed_prompt
    if not diagnosis.current_prompt_text:
        push_activity(
            f"HealingPipeline: prompt '{diagnosis.current_prompt_name}' not in Phoenix — using seed prompt",
            "warn",
        )

    # ── GENERATE ──────────────────────────────────────────────────────────────
    push_activity("HealingPipeline: mutation engine running (TextGrad)", "heal")
    try:
        mutation = await generate_candidate_prompt(
            current_prompt=effective_prompt,
            failing_examples=examples,
            query_type=diagnosis.query_type,
            failure_rate=diagnosis.hallucination_rate,
        )
    except Exception as exc:
        push_activity(f"HealingPipeline: mutation failed — {str(exc)[:100]}", "critical")
        print(f"[HealingPipeline] mutation EXCEPTION: {exc}")
        return None

    new_prompt = (mutation.get("new_prompt") or "").strip()
    if not new_prompt or new_prompt == effective_prompt.strip():
        push_activity("HealingPipeline: mutation produced no change — aborting", "warn")
        return None

    constraint = mutation.get("injected_constraint", "")
    push_activity(f"HealingPipeline: mutation complete — {constraint[:100]}", "heal")

    # ── VALIDATE ──────────────────────────────────────────────────────────────
    push_activity("HealingPipeline: validating candidate (re-running IRIS evaluators)", "heal")
    validation = await validate_heal(
        old_prompt=effective_prompt,
        new_prompt=new_prompt,
        failing_examples=examples,
        query_type=diagnosis.query_type,
    )
    print(
        f"[HealingPipeline] validation: before={validation['score_before']:.2f} "
        f"after={validation['score_after']:.2f} improvement={validation['improvement']:+.2f} "
        f"passed={validation['passed']}"
    )

    candidate = HealingCandidate(
        candidate_id=diagnosis.candidate_id,
        diagnosis=diagnosis,
        old_prompt_text=effective_prompt,
        new_prompt_text=new_prompt,
        injected_constraint=constraint,
        mutation_rationale=mutation.get("mutation_rationale", ""),
        validation_score_before=validation["score_before"],
        validation_score_after=validation["score_after"],
        improvement_score=validation["improvement"],
        validation_passed=validation["passed"],
        phoenix_dataset_name=diagnosis.dataset_name,
        experiment_id=validation.get("experiment_id"),
    )

    if not validation["passed"]:
        push_activity(
            f"HealingPipeline: validation FAILED — improvement {validation['improvement']:+.2f}"
            f" < threshold {settings.healing_improvement_threshold}",
            "warn",
        )
        candidate.status = "failed"
        healing_history.appendleft(candidate)
        return candidate

    push_activity(
        f"HealingPipeline: validation PASSED — {validation['score_before']:.2f} → "
        f"{validation['score_after']:.2f} ({validation['improvement']:+.2f})",
        "heal",
    )

    # ── GATE / DEPLOY ─────────────────────────────────────────────────────────
    if settings.healing_auto_approve:
        candidate = await _deploy_candidate(candidate)
    else:
        candidate.status = "pending"
        healing_candidates.appendleft(candidate)
        push_activity(
            f"HealingPipeline: candidate {candidate.candidate_id[:8]} queued for human approval",
            "heal",
        )

    return candidate


async def approve_candidate(candidate_id: str) -> HealingCandidate | None:
    candidate = _find_candidate(candidate_id)
    if candidate is None:
        return None
    if candidate.status != "pending":
        return candidate
    candidate = await _deploy_candidate(candidate)
    _remove_from_pending(candidate_id)
    return candidate


async def reject_candidate(candidate_id: str, reason: str = "") -> HealingCandidate | None:
    candidate = _find_candidate(candidate_id)
    if candidate is None:
        return None
    candidate.status = "rejected"
    candidate.rejected_at = datetime.utcnow()
    candidate.rejection_reason = reason or "Human reviewer rejected the candidate"
    _remove_from_pending(candidate_id)
    healing_history.appendleft(candidate)
    push_activity(f"Candidate {candidate_id[:8]} rejected by human reviewer", "warn")
    return candidate


async def _deploy_candidate(candidate: HealingCandidate) -> HealingCandidate:
    description = (
        f"IRIS auto-heal: {candidate.injected_constraint[:100]}... "
        f"(improvement={candidate.improvement_score:+.2f}, cluster={candidate.diagnosis.query_type})"
    )
    version_data = await prompt_manager.create_prompt_version(
        prompt_name=candidate.diagnosis.current_prompt_name,
        template=candidate.new_prompt_text,
        description=description,
        temperature=0.1,
    )

    now = datetime.utcnow()
    if version_data:
        version_id = version_data.get("id") or version_data.get("version", {}).get("id")
        candidate.phoenix_prompt_version_id = version_id
        if version_id:
            tag = "production" if settings.healing_auto_approve else "candidate"
            await prompt_manager.tag_prompt_version(version_id, tag)
            candidate.status = "auto_approved" if settings.healing_auto_approve else "deployed"
            if settings.healing_auto_approve:
                candidate.approved_at = now
        else:
            candidate.status = "deployed"
        push_activity(
            f"Prompt deployed: {candidate.diagnosis.current_prompt_name} "
            f"(v{version_id or 'unknown'}) improvement={candidate.improvement_score:+.2f}",
            "heal",
        )
    else:
        candidate.status = "deployed"
        push_activity("Prompt approved locally (Phoenix write failed)", "warn")

    candidate.deployed_at = now
    shift_stats["self_heals"] = shift_stats.get("self_heals", 0) + 1
    healing_history.appendleft(candidate)
    return candidate


def _find_candidate(candidate_id: str) -> HealingCandidate | None:
    for c in healing_candidates:
        if c.candidate_id == candidate_id:
            return c
    return None


def _remove_from_pending(candidate_id: str) -> None:
    remaining = [c for c in healing_candidates if c.candidate_id != candidate_id]
    healing_candidates.clear()
    for c in remaining:
        healing_candidates.append(c)
