"""
TextGrad-style prompt mutation engine.

Implements a two-pass approach inspired by TextGrad (Yuksekgonul et al., Nature 2024):

  Pass 1 — Per-example "textual gradient":
    For each failing span, Gemini explains WHY the current prompt failed to prevent
    the failure — what specific instruction was missing or unclear.

  Pass 2 — Gradient synthesis:
    Gemini aggregates the per-example gradients into a single targeted constraint
    that is specific to the failure mode — not a generic safety platitude.

This produces mutation hypotheses that are causally linked to observed failures,
unlike random perturbation or generic "be more careful" injections.
"""
from __future__ import annotations

import json

from google import genai
from google.genai import types as genai_types

from core.config import settings

_genai_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _genai_client
    if _genai_client is None:
        _genai_client = genai.Client(api_key=settings.google_api_key)
    return _genai_client


_GRADIENT_PER_EXAMPLE_PROMPT = """\
You are analyzing why a clinical AI prompt failed to produce a safe response.

Current prompt given to the clinical AI agent:
---
{current_prompt}
---

Failure example {example_num}/{total_examples}:
  Query type: {query_type}
  Input question: {input_prompt}
  Agent's unsafe response: {output_text}
  Safety violation: {violation_description}
  Safety score: {score}/10 (FAIL)

Analyze specifically:
1. Which part of the current prompt should have prevented this failure?
2. What instruction was missing, ambiguous, or too weak to prevent it?
3. Write ONE specific instruction (1-2 sentences max) that, if added to the prompt,
   would have made this exact failure less likely. Be concrete and clinical.

Respond ONLY with valid JSON:
{{
  "missing_instruction": "<the specific missing instruction>",
  "failure_mode": "<drug_hallucination|dosage_overdose|phase_violation|context_gap|attribution_error|other>",
  "root_cause": "<1 sentence: why the current prompt didn't prevent this>"
}}
"""

_GRADIENT_SYNTHESIS_PROMPT = """\
You are synthesizing analysis from {n_examples} clinical AI failure cases to improve
a safety prompt. Your goal is to produce ONE targeted constraint that addresses the
dominant failure pattern — not a generic safety platitude.

Current prompt:
---
{current_prompt}
---

Per-example failure analyses (textual gradients):
{gradients_text}

Failure cluster summary:
  Query type: {query_type}
  Failure rate: {failure_rate:.0%}
  Dominant failure mode: {dominant_mode}

Synthesize a SINGLE targeted constraint injection that:
1. Directly addresses the root cause shared across these failures
2. Is specific enough to prevent the exact failure mode
3. Is concise (2-3 sentences max) and written for a clinical AI agent
4. Will not degrade performance on queries that were already passing

Do NOT write generic advice like "always be careful" or "verify everything."
Write a precise, actionable clinical safety instruction.

Respond ONLY with valid JSON:
{{
  "injected_constraint": "<the targeted constraint text, 2-3 sentences>",
  "mutation_rationale": "<1 sentence: why this constraint addresses the root cause>",
  "new_prompt": "<the complete updated prompt with the constraint injected at the end>",
  "confidence": <float 0.0-1.0, how confident you are this will improve safety>
}}
"""


async def generate_candidate_prompt(
    current_prompt: str,
    failing_examples: list[dict],
    query_type: str,
    failure_rate: float,
) -> dict:
    """
    Given the current clinical AI prompt and a list of failing examples,
    generate a mutated prompt with a targeted safety constraint.

    Returns:
        {
            "injected_constraint": str,
            "mutation_rationale": str,
            "new_prompt": str,
            "confidence": float,
            "gradients": list[dict]   # per-example analysis
        }
    """
    # Pass 1: per-example textual gradients
    gradients: list[dict] = []
    for i, example in enumerate(failing_examples):
        gradient = await _compute_example_gradient(
            current_prompt=current_prompt,
            example=example,
            example_num=i + 1,
            total_examples=len(failing_examples),
            query_type=query_type,
        )
        if gradient:
            gradients.append(gradient)

    if not gradients:
        # Fallback: single-pass direct mutation
        return await _fallback_mutation(current_prompt, query_type, failure_rate)

    # Pass 2: synthesize gradients into one targeted constraint
    dominant_mode = _dominant_failure_mode(gradients)
    gradients_text = _format_gradients(gradients)

    synthesis = await _synthesize_gradients(
        current_prompt=current_prompt,
        gradients_text=gradients_text,
        query_type=query_type,
        failure_rate=failure_rate,
        dominant_mode=dominant_mode,
        n_examples=len(gradients),
    )

    if synthesis is None:
        return await _fallback_mutation(current_prompt, query_type, failure_rate)

    return {**synthesis, "gradients": gradients}


async def _compute_example_gradient(
    current_prompt: str,
    example: dict,
    example_num: int,
    total_examples: int,
    query_type: str,
) -> dict | None:
    prompt = _GRADIENT_PER_EXAMPLE_PROMPT.format(
        current_prompt=current_prompt[:800],
        example_num=example_num,
        total_examples=total_examples,
        query_type=query_type,
        input_prompt=example.get("input_prompt", "")[:300],
        output_text=example.get("output_text", "")[:400],
        violation_description=example.get("violation", "Safety evaluation failed")[:200],
        score=example.get("score", 0),
    )
    try:
        response = await _get_client().aio.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
                seed=42,
            ),
        )
        if not response.text:
            raise ValueError("empty gradient response")
        return json.loads(response.text)
    except Exception as exc:
        print(f"[MutationEngine] Gradient computation failed for example {example_num}: {exc}")
        return None


async def _synthesize_gradients(
    current_prompt: str,
    gradients_text: str,
    query_type: str,
    failure_rate: float,
    dominant_mode: str,
    n_examples: int,
) -> dict | None:
    prompt = _GRADIENT_SYNTHESIS_PROMPT.format(
        current_prompt=current_prompt[:800],
        gradients_text=gradients_text,
        query_type=query_type,
        failure_rate=failure_rate,
        dominant_mode=dominant_mode,
        n_examples=n_examples,
    )
    try:
        response = await _get_client().aio.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
                seed=42,
            ),
        )
        if not response.text:
            raise ValueError("empty synthesis response")
        return json.loads(response.text)
    except Exception as exc:
        print(f"[MutationEngine] Gradient synthesis failed: {exc}")
        return None


async def _fallback_mutation(current_prompt: str, query_type: str, failure_rate: float) -> dict:
    """Single-pass mutation when per-example gradients fail."""
    fallback_constraints = {
        "drug_dosage": (
            "SAFETY CRITICAL: Before stating any drug dose, verify it is within the "
            "FDA-approved range for this patient's weight and renal function (creatinine clearance). "
            "If creatinine clearance is unknown, state this explicitly and do not recommend a specific dose."
        ),
        "drug_interaction": (
            "SAFETY CRITICAL: Only reference drug names that exist in RxNorm. "
            "If uncertain of a drug name's spelling or existence, state the uncertainty "
            "rather than proceeding with a potentially incorrect name."
        ),
        "procedure": (
            "SAFETY CRITICAL: Before recommending any intervention, confirm it is clinically "
            "appropriate for the current surgical phase. Recommendations that are phase-inappropriate "
            "must be explicitly flagged and deferred to the attending physician."
        ),
    }
    constraint = fallback_constraints.get(
        query_type,
        "SAFETY CRITICAL: Verify all clinical claims against the patient's documented record before stating them.",
    )
    new_prompt = current_prompt.rstrip() + f"\n\n{constraint}"
    return {
        "injected_constraint": constraint,
        "mutation_rationale": f"Fallback constraint for {query_type} failures (gradient computation unavailable)",
        "new_prompt": new_prompt,
        "confidence": 0.5,
        "gradients": [],
    }


def _dominant_failure_mode(gradients: list[dict]) -> str:
    modes = [g.get("failure_mode", "other") for g in gradients]
    if not modes:
        return "other"
    return max(set(modes), key=modes.count)


def _format_gradients(gradients: list[dict]) -> str:
    lines = []
    for i, g in enumerate(gradients, 1):
        lines.append(
            f"Example {i}:\n"
            f"  Failure mode: {g.get('failure_mode', 'unknown')}\n"
            f"  Root cause: {g.get('root_cause', '')}\n"
            f"  Missing instruction: {g.get('missing_instruction', '')}"
        )
    return "\n\n".join(lines)
