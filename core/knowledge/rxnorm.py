"""
RxNorm public API client.
No API key required. Used for drug name validation and dose range lookup.
"""
from __future__ import annotations

import asyncio
import json
import re

import httpx

RXNAV_BASE = "https://rxnav.nlm.nih.gov/REST"


class RxNormUnavailable(Exception):
    """RxNav API could not be reached — 'unknown', not 'drug does not exist'."""


async def lookup_rxcui(drug_name: str, raise_on_error: bool = False) -> str | None:
    """Return the RxCUI for a drug name, or None if not found.

    Retries once. On persistent API failure returns None, or raises
    RxNormUnavailable when raise_on_error is set — safety-critical callers
    must distinguish an outage from a genuinely unknown drug.
    """
    url = f"{RXNAV_BASE}/rxcui.json"
    last_exc: Exception | None = None
    for attempt in range(2):
        async with httpx.AsyncClient(timeout=8) as client:
            try:
                resp = await client.get(url, params={"name": drug_name, "search": "1"})
                resp.raise_for_status()
                data = resp.json()
                cuis = data.get("idGroup", {}).get("rxnormId", [])
                return cuis[0] if cuis else None
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt == 0:
                    await asyncio.sleep(0.4)
    if raise_on_error:
        raise RxNormUnavailable(str(last_exc))
    return None


async def is_valid_drug(drug_name: str) -> tuple[bool | None, str | None]:
    """
    Returns (is_valid, rxcui).
    True  — RxNorm knows this drug.
    False — RxNorm definitively does not know it (likely hallucinated).
    None  — RxNorm unreachable: unknown, must NOT be flagged as a hallucination.
    """
    try:
        rxcui = await lookup_rxcui(drug_name, raise_on_error=True)
    except RxNormUnavailable:
        return None, None
    return (rxcui is not None), rxcui


async def get_drug_dose_ranges(rxcui: str) -> list[dict]:
    """
    Fetch dosage form + strength data from RxNorm for a given RxCUI.
    Returns a list of dicts with keys: strength, dose_form, unit.
    """
    url = f"{RXNAV_BASE}/rxcui/{rxcui}/related.json"
    async with httpx.AsyncClient(timeout=8) as client:
        try:
            resp = await client.get(url, params={"tty": "SCD+SCDF"})
            resp.raise_for_status()
            data = resp.json()
            concepts = (
                data.get("relatedGroup", {})
                .get("conceptGroup", [])
            )
            results = []
            for group in concepts:
                for prop in group.get("conceptProperties", []):
                    name = prop.get("name", "")
                    # Parse strength from concept name, e.g. "metformin 500 MG Oral Tablet"
                    match = re.search(r"(\d+(?:\.\d+)?)\s*(MG|MCG|MEQ|UNIT|ML)", name, re.I)
                    if match:
                        results.append({
                            "name": name,
                            "strength": float(match.group(1)),
                            "unit": match.group(2).upper(),
                        })
            return results
        except httpx.HTTPError:
            return []


_EXTRACT_PROMPT = """\
You are a clinical pharmacist extracting medication mentions from clinical text.

Extract every drug name and its stated dose from the text below.
Include only explicitly stated doses — do not infer or assume.
Normalise unit spelling (e.g. "milligrams" → "mg", "micrograms" → "mcg").

Text:
\"\"\"
{text}
\"\"\"

Return ONLY a JSON array. Each element must have exactly these keys:
  "drug"  — the drug name as written (string)
  "dose"  — the numeric dose value (number)
  "unit"  — the dose unit (string: mg | mcg | g | mEq | units | ml | mg/kg)

If no drug doses are mentioned, return an empty array [].
No explanation, no markdown — just the JSON array.
"""

_llm_client = None


def _get_llm_client():
    global _llm_client
    if _llm_client is None:
        from google import genai
        from core.config import settings
        _llm_client = genai.Client(
            vertexai=True,
            project=settings.google_cloud_project,
            location=settings.google_cloud_location,
        )
    return _llm_client


async def extract_drug_doses(text: str) -> list[dict]:
    """
    LLM-powered drug name + dose extraction from clinical free text.
    Returns list of {drug, dose, unit} dicts. Falls back to [] on failure.
    """
    from core.llm import generate_json

    try:
        mentions = await generate_json(
            _EXTRACT_PROMPT.format(text=text.strip()),
            temperature=0.0,
            seed=42,
            tag="DrugExtract",
        )
        if not isinstance(mentions, list):
            return []
        # Normalise: ensure dose is float, filter malformed entries
        result = []
        for m in mentions:
            if isinstance(m, dict) and "drug" in m and "dose" in m and "unit" in m:
                try:
                    result.append({
                        "drug": str(m["drug"]).strip(),
                        "dose": float(m["dose"]),
                        "unit": str(m["unit"]).strip().lower(),
                    })
                except (ValueError, TypeError):
                    continue
        return result
    except Exception as exc:
        print(f"[rxnorm] LLM extraction failed: {exc}")
        return []
