"""
OpenFDA drug label client.
Fetches prescribing information (dosing, renal adjustment, contraindications)
from the public OpenFDA API — no API key required.
"""
from __future__ import annotations

import asyncio
from functools import lru_cache

import httpx

OPENFDA_BASE = "https://api.fda.gov/drug/label.json"

_LABEL_CACHE: dict[str, dict | None] = {}


async def fetch_label(drug_name: str) -> dict | None:
    """
    Fetch the first matching FDA drug label for a drug name.
    Returns a dict with relevant label sections, or None if not found.
    Cached in-memory for the session (keyed by lowercased drug name).
    """
    key = drug_name.lower().strip()
    if key in _LABEL_CACHE:
        return _LABEL_CACHE[key]

    params = {
        "search": f'openfda.generic_name:"{drug_name}"',
        "limit": 1,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(OPENFDA_BASE, params=params)
            if resp.status_code == 404:
                # Try by brand name as fallback
                params["search"] = f'openfda.brand_name:"{drug_name}"'
                resp = await client.get(OPENFDA_BASE, params=params)
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if not results:
                _LABEL_CACHE[key] = None
                return None

            label = results[0]
            extracted = {
                "dosage_and_administration": _first(label, "dosage_and_administration"),
                "warnings": _first(label, "warnings"),
                "contraindications": _first(label, "contraindications"),
                "warnings_and_cautions": _first(label, "warnings_and_cautions"),
                "renal_adjustment": _first(label, "renal_impairment") or _first(label, "use_in_specific_populations"),
                "openfda": label.get("openfda", {}),
            }
            _LABEL_CACHE[key] = extracted
            return extracted
        except httpx.HTTPError:
            _LABEL_CACHE[key] = None
            return None


def _first(label: dict, key: str) -> str | None:
    val = label.get(key)
    if isinstance(val, list) and val:
        return val[0]
    return val or None


def clear_cache() -> None:
    _LABEL_CACHE.clear()
