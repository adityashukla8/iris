"""
Log real clinical failure examples to a Phoenix dataset.

A Phoenix *dataset* is a saved set of (input, expected output) rows that an
*experiment* can later be run against. We log the actual failing input/output
pulled from live traces (not stubs), so the dataset is a faithful record of what
went wrong and a fixture the healing experiment can validate against.

Uses the arize-phoenix SDK if installed; degrades to a no-op (non-fatal) otherwise
so the heal loop still runs. Returns (dataset_id_or_name, n_examples_logged).
"""
from __future__ import annotations

from core.config import settings
from core.state import push_activity


async def log_failure_examples(
    dataset_name: str,
    examples: list[dict],
    query_type: str,
) -> tuple[str | None, int]:
    if not examples:
        return None, 0

    inputs = [
        {"query_type": query_type, "input_prompt": ex.get("input_prompt", "")}
        for ex in examples
    ]
    outputs = [
        {
            "unsafe_output": ex.get("output_text", ""),
            "violation": ex.get("violation", ""),
            "iris_score": ex.get("score", 0.0),
        }
        for ex in examples
    ]

    try:
        import pandas as pd  # noqa: F401
        from phoenix.client import Client  # arize-phoenix >= 6.0 or arize-phoenix-client

        df = _build_dataframe(inputs, outputs)
        client = Client(base_url=settings.phoenix_client_url, api_key=settings.phoenix_api_key)
        # Each create_dataset call with the same name creates a new version in Phoenix —
        # this gives a timestamped record of failures across healing runs.
        ds = await _run_blocking(
            client.datasets.create_dataset,
            name=dataset_name,
            dataframe=df,
            input_keys=["query_type", "input_prompt"],
            output_keys=["unsafe_output", "violation", "iris_score"],
        )
        ds_id = getattr(ds, "id", None) or dataset_name
        push_activity(f"Healing: logged {len(examples)} example(s) to dataset '{dataset_name}'", "heal")
        return str(ds_id), len(examples)
    except Exception as exc:
        push_activity(f"Healing: dataset logging skipped ({str(exc)[:80]})", "warn")
        print(f"[HealingDataset] dataset logging unavailable: {exc}")
        return None, 0


def _build_dataframe(inputs: list[dict], outputs: list[dict]):
    import pandas as pd

    rows = []
    for i, o in zip(inputs, outputs):
        rows.append({**i, **o})
    return pd.DataFrame(rows)


async def _run_blocking(fn, **kwargs):
    import asyncio

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: fn(**kwargs))
