"""
Log real clinical failure examples to a Phoenix dataset.

A Phoenix *dataset* is a versioned set of (input, output, metadata) rows that an
*experiment* can later run against. The three-partition schema matters:
  - input  : everything the task function needs to re-run the scenario
  - output : the original unsafe response (baseline for improvement comparison)
  - metadata: tracking fields for filtering/attribution in the Phoenix UI

We log the actual failing input/output pulled from live traces (not stubs), so the
dataset is a faithful record of what went wrong and a regression fixture for future
prompt experiments.

Uses the arize-phoenix SDK if installed; degrades to a no-op (non-fatal) so the
heal loop continues even when dataset logging fails.
Returns (dataset_id_or_name, n_examples_logged).
"""
from __future__ import annotations

import json

from core.config import settings
from core.state import push_activity


async def log_failure_examples(
    dataset_name: str,
    examples: list[dict],
    query_type: str,
) -> tuple[str | None, int]:
    if not examples:
        return None, 0

    # Input: everything needed to replay the scenario in a Phoenix experiment.
    # The evaluators need system_prompt + retrieved_context + surgical_phase to re-score.
    inputs = [
        {
            "input_prompt": ex.get("input_prompt", ""),
            "system_prompt": ex.get("system_prompt", ""),
            "query_type": query_type,
            "retrieved_context": json.dumps(ex.get("retrieved_context") or {}),
            "surgical_phase": ex.get("surgical_phase") or "",
        }
        for ex in examples
    ]

    # Output: the original unsafe response — serves as the baseline for improvement.
    # "original_" prefix signals these are pre-heal reference values, not ground truth.
    outputs = [
        {
            "unsafe_output": ex.get("output_text", ""),
            "original_violation": ex.get("violation", ""),
            "original_score": float(ex.get("score", 0.0)),
        }
        for ex in examples
    ]

    # Metadata: attribution and filtering in the Phoenix UI.
    metadata = [
        {
            "agent_name": ex.get("agent_name", "unknown"),
            "prompt_hash": ex.get("prompt_hash", "none"),
            "agent_version": ex.get("agent_version", "unknown"),
        }
        for ex in examples
    ]

    try:
        import pandas as pd  # noqa: F401
        from phoenix.client import Client  # arize-phoenix >= 6.0 or arize-phoenix-client

        df = _build_dataframe(inputs, outputs, metadata)
        client = Client(base_url=settings.phoenix_client_url, api_key=settings.phoenix_api_key)
        # Each create_dataset call with the same name creates a new version in Phoenix —
        # timestamped record of failures across healing runs.
        ds = await _run_blocking(
            client.datasets.create_dataset,
            name=dataset_name,
            dataframe=df,
            input_keys=["input_prompt", "system_prompt", "query_type", "retrieved_context", "surgical_phase"],
            output_keys=["unsafe_output", "original_violation", "original_score"],
            metadata_keys=["agent_name", "prompt_hash", "agent_version"],
        )
        ds_id = getattr(ds, "id", None) or dataset_name
        push_activity(f"Healing: logged {len(examples)} example(s) to dataset '{dataset_name}'", "heal")
        return str(ds_id), len(examples)
    except Exception as exc:
        push_activity(f"Healing: dataset logging skipped ({str(exc)[:80]})", "warn")
        print(f"[HealingDataset] dataset logging unavailable: {exc}")
        return None, 0


def _build_dataframe(inputs: list[dict], outputs: list[dict], metadata: list[dict]):
    import pandas as pd

    rows = []
    for i, o, m in zip(inputs, outputs, metadata):
        rows.append({**i, **o, **m})
    return pd.DataFrame(rows)


async def _run_blocking(fn, **kwargs):
    import asyncio

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: fn(**kwargs))
