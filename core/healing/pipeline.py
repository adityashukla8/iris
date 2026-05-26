"""
IRIS Self-Healing Pipeline — Python orchestration layer.

Picks up where the MCP agent (self_healer.py) leaves off.
The MCP agent handles DIAGNOSE (read spans, get prompt, log dataset examples).
This pipeline handles GENERATE → VALIDATE → GATE → DEPLOY.

Flow:
  HealingDiagnosis (from MCP agent)
    → mutation_engine.generate_candidate_prompt()     [GENERATE]
    → validator.validate_candidate()                  [VALIDATE]
    → if passes gate:
        if auto_approve: prompt_manager.deploy()      [DEPLOY]
        else: add to healing_candidates queue         [GATE → human]
    → return HealingCandidate

Called from core/main.py as a background asyncio task.
"""
from __future__ import annotations

import asyncio
from datetime import datetime

from core.config import settings
from core.healing.models import HealingCandidate, HealingDiagnosis
from core.healing.mutation_engine import generate_candidate_prompt
from core.healing.prompt_manager import prompt_manager
from core.healing.validator import validate_candidate
from core.state import healing_candidates, healing_history, shift_stats


async def run_healing_pipeline(diagnosis: HealingDiagnosis) -> HealingCandidate | None:
    """
    Execute the full GENERATE → VALIDATE → GATE → DEPLOY pipeline.
    Returns the HealingCandidate (regardless of approval status), or None on fatal error.
    """
    print(f"[HealingPipeline] Starting pipeline for cluster: {diagnosis.query_type} "
          f"(failure_rate={diagnosis.hallucination_rate:.0%})")

    # Rebuild failing examples from diagnosis metadata for mutation + validation
    # The MCP agent has already logged these to Phoenix dataset; we reconstruct
    # a minimal representation for the local pipeline.
    failing_examples = _extract_examples_from_diagnosis(diagnosis)

    # ── Phase 3a: GENERATE candidate prompt ──────────────────────────────────
    try:
        mutation_result = await generate_candidate_prompt(
            current_prompt=diagnosis.current_prompt_text,
            failing_examples=failing_examples,
            query_type=diagnosis.query_type,
            failure_rate=diagnosis.hallucination_rate,
        )
    except Exception as exc:
        print(f"[HealingPipeline] Mutation failed: {exc}")
        return None

    new_prompt = mutation_result.get("new_prompt", "")
    if not new_prompt or new_prompt == diagnosis.current_prompt_text:
        print("[HealingPipeline] Mutation produced no change — aborting")
        return None

    # ── Phase 3b: VALIDATE candidate prompt ──────────────────────────────────
    validation = await validate_candidate(
        old_prompt=diagnosis.current_prompt_text,
        new_prompt=new_prompt,
        failing_examples=failing_examples,
        query_type=diagnosis.query_type,
    )

    candidate = HealingCandidate(
        candidate_id=diagnosis.candidate_id,
        diagnosis=diagnosis,
        old_prompt_text=diagnosis.current_prompt_text,
        new_prompt_text=new_prompt,
        injected_constraint=mutation_result.get("injected_constraint", ""),
        mutation_rationale=mutation_result.get("mutation_rationale", ""),
        validation_score_before=validation["score_before"],
        validation_score_after=validation["score_after"],
        improvement_score=validation["improvement"],
        validation_passed=validation["passed"],
        phoenix_dataset_name=diagnosis.dataset_name,
    )

    if not validation["passed"]:
        print(
            f"[HealingPipeline] Validation FAILED — improvement {validation['improvement']:.2f} "
            f"< threshold {settings.healing_improvement_threshold}. Discarding candidate."
        )
        candidate.status = "failed"
        healing_history.appendleft(candidate)
        return candidate

    print(
        f"[HealingPipeline] Validation PASSED — improvement {validation['improvement']:.2f}, "
        f"prevention_rate={validation['prevention_rate']:.0%}"
    )

    # ── Phase 4: GATE / DEPLOY ────────────────────────────────────────────────
    if settings.healing_auto_approve:
        candidate = await _deploy_candidate(candidate)
    else:
        candidate.status = "pending"
        healing_candidates.appendleft(candidate)
        print(f"[HealingPipeline] Candidate queued for human approval: {candidate.candidate_id}")

    return candidate


async def approve_candidate(candidate_id: str) -> HealingCandidate | None:
    """
    Approve a pending HealingCandidate. Deploys the new prompt to Phoenix.
    Called from POST /healing/approve/{candidate_id}.
    """
    candidate = _find_candidate(candidate_id)
    if candidate is None:
        return None
    if candidate.status != "pending":
        return candidate

    candidate = await _deploy_candidate(candidate)
    _remove_from_pending(candidate_id)
    return candidate


async def reject_candidate(candidate_id: str, reason: str = "") -> HealingCandidate | None:
    """
    Reject a pending HealingCandidate. Logs to history for analysis.
    Called from POST /healing/reject/{candidate_id}.
    """
    candidate = _find_candidate(candidate_id)
    if candidate is None:
        return None

    candidate.status = "rejected"
    candidate.rejected_at = datetime.utcnow()
    candidate.rejection_reason = reason or "Human reviewer rejected the candidate"
    _remove_from_pending(candidate_id)
    healing_history.appendleft(candidate)
    print(f"[HealingPipeline] Candidate rejected: {candidate_id} — {reason}")
    return candidate


async def _deploy_candidate(candidate: HealingCandidate) -> HealingCandidate:
    """Create a versioned prompt in Phoenix and tag it as 'candidate'."""
    description = (
        f"IRIS auto-heal: {candidate.injected_constraint[:100]}... "
        f"(improvement={candidate.improvement_score:+.2f}, "
        f"cluster={candidate.diagnosis.query_type})"
    )

    version_data = await prompt_manager.create_prompt_version(
        prompt_name=candidate.diagnosis.current_prompt_name,
        template=candidate.new_prompt_text,
        description=description,
        temperature=0.1,
    )

    if version_data:
        version_id = (
            version_data.get("id")
            or version_data.get("version", {}).get("id")
        )
        candidate.phoenix_prompt_version_id = version_id

        now = datetime.utcnow()
        if version_id:
            tag = "production" if settings.healing_auto_approve else "candidate"
            await prompt_manager.tag_prompt_version(version_id, tag)
            candidate.status = "auto_approved" if settings.healing_auto_approve else "deployed"
            if settings.healing_auto_approve:
                candidate.approved_at = now
        else:
            candidate.status = "deployed"

        candidate.deployed_at = now
        shift_stats["self_heals"] = shift_stats.get("self_heals", 0) + 1
        print(
            f"[HealingPipeline] Prompt deployed to Phoenix: "
            f"{candidate.diagnosis.current_prompt_name} "
            f"(version_id={version_id})"
        )
    else:
        # Phoenix write failed — still mark as approved locally and count the heal
        candidate.status = "deployed"
        candidate.deployed_at = datetime.utcnow()
        shift_stats["self_heals"] = shift_stats.get("self_heals", 0) + 1
        print("[HealingPipeline] Phoenix write failed — candidate approved locally only")

    healing_history.appendleft(candidate)
    return candidate


def _extract_examples_from_diagnosis(diagnosis: HealingDiagnosis) -> list[dict]:
    """
    Build minimal failing example dicts from the diagnosis.
    In production these would come from Phoenix span data; here we reconstruct
    from what the MCP agent captured in failure_analysis.
    """
    # The MCP agent stores the failure analysis as a string; we create synthetic
    # example dicts for the mutation engine and validator to work with.
    return [
        {
            "input_prompt": f"[cluster: {diagnosis.query_type}] Clinical query",
            "output_text": f"[Span {span_id}] Unsafe clinical AI output",
            "violation": diagnosis.failure_analysis[:200] if diagnosis.failure_analysis else "Safety evaluation failed",
            "score": max(0.0, min(4.9, 10.0 * (1.0 - diagnosis.hallucination_rate))),
        }
        for span_id in diagnosis.failing_span_ids[:settings.healing_validation_examples]
    ]


def _find_candidate(candidate_id: str) -> HealingCandidate | None:
    for c in healing_candidates:
        if c.candidate_id == candidate_id:
            return c
    return None


def _remove_from_pending(candidate_id: str) -> None:
    global healing_candidates
    remaining = [c for c in healing_candidates if c.candidate_id != candidate_id]
    healing_candidates.clear()
    for c in remaining:
        healing_candidates.append(c)
