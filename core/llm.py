"""
Shared Gemini gateway — one client, one concurrency throttle, one retry policy.

Every Gemini call in the evaluation and healing paths routes through here.
Rationale: a simulation run fans out to ~8 calls per event (7 judges + drug
extraction), and heal validation regenerates 5 examples concurrently — 40+
simultaneous Vertex requests. gemini-2.5-flash runs on dynamic shared quota,
so unthrottled bursts get 429 RESOURCE_EXHAUSTED, and a single malformed-JSON
response (ordinary temperature>0 flakiness) used to silently degrade an
evaluator to its fallback score. The semaphore smooths the burst; 429s back
off and retry; broken JSON is re-asked once.
"""
from __future__ import annotations

import asyncio
import json
import random

from google import genai
from google.genai import types as genai_types

from core.config import settings

_client: genai.Client | None = None
_semaphore: asyncio.Semaphore | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(
            vertexai=True,
            project=settings.google_cloud_project,
            location=settings.google_cloud_location,
        )
    return _client


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(settings.gemini_max_concurrency)
    return _semaphore


def _is_retryable(exc: Exception) -> bool:
    msg = str(exc)
    return any(s in msg for s in ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE"))


async def generate_text(
    prompt: str,
    *,
    model: str | None = None,
    temperature: float = 0.1,
    seed: int | None = None,
    json_mode: bool = False,
    tag: str = "llm",
) -> str | None:
    """Throttled generate_content with backoff retry on quota/availability
    errors. Returns the response text, or None after exhausting retries."""
    config = genai_types.GenerateContentConfig(
        temperature=temperature,
        seed=seed,
        response_mime_type="application/json" if json_mode else None,
    )
    for attempt in range(settings.gemini_retries + 1):
        try:
            async with _get_semaphore():
                response = await _get_client().aio.models.generate_content(
                    model=model or settings.eval_gemini_model,
                    contents=prompt,
                    config=config,
                )
            return response.text
        except Exception as exc:
            if _is_retryable(exc) and attempt < settings.gemini_retries:
                delay = 2 ** attempt + random.uniform(0, 0.5)
                print(
                    f"[{tag}] Gemini throttled/unavailable — "
                    f"retry {attempt + 1}/{settings.gemini_retries} in {delay:.1f}s"
                )
                await asyncio.sleep(delay)
                continue
            print(f"[{tag}] Gemini call failed: {exc}")
            return None
    return None


def _coerce_json(text: str) -> dict | list | None:
    """Parse model output as JSON, salvaging the outermost object/array if the
    payload is wrapped in prose/fences or has trailing junk."""
    s = text.strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start, end = s.find(open_c), s.rfind(close_c)
        if start != -1 and end > start:
            try:
                return json.loads(s[start:end + 1])
            except json.JSONDecodeError:
                continue
    return None


async def generate_json(
    prompt: str,
    *,
    model: str | None = None,
    temperature: float = 0.1,
    seed: int | None = None,
    tag: str = "llm",
) -> dict | list | None:
    """generate_text in JSON mode; re-asks when the model emits broken JSON.

    The re-ask bumps temperature: at near-zero temperature an identical retry
    deterministically reproduces the same malformed output.
    """
    for attempt in range(2):
        text = await generate_text(
            prompt,
            model=model,
            temperature=temperature + 0.4 * attempt,
            seed=seed,
            json_mode=True,
            tag=tag,
        )
        if text is None:
            return None
        parsed = _coerce_json(text)
        if parsed is not None:
            return parsed
        if attempt == 0:
            print(f"[{tag}] Malformed JSON from Gemini — re-asking at higher temperature")
    print(f"[{tag}] Gemini call failed: malformed JSON twice")
    return None
