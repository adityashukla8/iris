"""
Phoenix observability client for IRIS eval results.

Two complementary paths, both keyed to the SAME span (the IRIS event span opened
in the /event handler):

  1. OTel span attributes (`iris.eval.*`) — render under the span's Attributes tab.
     Always written while the span is open.
  2. REST /v1/span_annotations — render under the span's Annotations tab and make
     the trace "evaluable" in the Phoenix UI. Written AFTER the span is flushed,
     keyed by the span's OTel hex id, with a short retry for ingestion lag.

The previous implementation wrote the annotation during evaluation (before the
batched span reached Phoenix) using whatever span happened to be current — so the
annotation 404'd and the Annotations tab stayed empty. Both bugs are fixed here.
"""
from __future__ import annotations

import asyncio
import json

import httpx
from opentelemetry import trace as otel_trace

from core.config import settings
from sdk.models import EvalResult, IrisEvent


def record_eval_on_span(span: otel_trace.Span, event: IrisEvent, result: EvalResult) -> None:
    """Write one eval result as attributes on the given span."""
    if span is None:
        return
    prefix = f"iris.eval.{result.evaluator}"
    span.set_attribute(f"{prefix}.score", result.score)
    span.set_attribute(f"{prefix}.severity", result.severity.value)
    span.set_attribute(f"{prefix}.passed", result.passed)
    span.set_attribute(f"{prefix}.rationale", result.rationale[:500])
    span.set_attribute(f"{prefix}.confidence", result.confidence)
    if result.flagged_claims:
        span.set_attribute(f"{prefix}.flagged_claims", "; ".join(result.flagged_claims)[:500])
    if result.reasoning_chain:
        span.set_attribute(f"{prefix}.reasoning", json.dumps(result.reasoning_chain)[:1000])


def record_event_on_span(span: otel_trace.Span, event: IrisEvent, phash: str = "") -> None:
    """Write the clinical event identity + I/O as attributes on the given span."""
    if span is None:
        return
    span.set_attribute("iris.agent_name", event.agent_name)
    span.set_attribute("iris.query_type", str(event.query_type))
    span.set_attribute("iris.trace_id", event.trace_id)
    span.set_attribute("input.value", event.input_prompt[:2000])
    span.set_attribute("output.value", event.output_text[:2000])
    if phash:
        span.set_attribute("iris.prompt_hash", phash)
    if event.system_prompt:
        span.set_attribute("iris.system_prompt", event.system_prompt[:500])
    if event.prompt_name:
        span.set_attribute("iris.prompt_name", event.prompt_name)
    if event.surgical_phase:
        span.set_attribute("iris.surgical_phase", str(event.surgical_phase))


def span_id_hex(span: otel_trace.Span) -> str | None:
    ctx = span.get_span_context() if span else None
    if ctx and ctx.is_valid:
        return format(ctx.span_id, "016x")
    return None


class PhoenixClient:
    def __init__(self) -> None:
        self._base_url = settings.phoenix_client_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {settings.phoenix_api_key}",
            "Content-Type": "application/json",
        }

    async def annotate_span(
        self,
        span_id: str,
        event: IrisEvent,
        results: list[EvalResult],
        max_retries: int = 3,
    ) -> bool:
        """
        Write eval results as Phoenix span annotations for an already-exported span.
        Batches all evaluators into one POST. Retries on 404 (span not ingested yet).
        """
        if not span_id or not results:
            return False

        payload = {
            "data": [
                {
                    "span_id": span_id,
                    "name": r.evaluator,
                    "annotator_kind": "LLM" if r.metadata.get("llm_judged") else "CODE",
                    "result": {
                        "label": r.severity.value.upper(),
                        "score": round(r.score / 10.0, 3),
                        "explanation": r.rationale[:1000],
                    },
                    "metadata": {
                        "agent_name": event.agent_name,
                        "query_type": str(event.query_type),
                        "iris_trace_id": event.trace_id,
                        "passed": r.passed,
                        "confidence": r.confidence,
                    },
                }
                for r in results
            ]
        }

        backoff = 1.0
        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(
                        f"{self._base_url}/v1/span_annotations",
                        json=payload,
                        headers=self._headers,
                    )
                    if resp.status_code == 404 and attempt < max_retries:
                        await asyncio.sleep(backoff)
                        backoff *= 1.5
                        continue
                    resp.raise_for_status()
                    return True
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404 and attempt < max_retries:
                    await asyncio.sleep(backoff)
                    backoff *= 1.5
                    continue
                print(
                    f"[Phoenix] annotation {exc.response.status_code} for span {span_id}: "
                    f"{exc.response.text[:150]}"
                )
                return False
            except httpx.HTTPError as exc:
                print(f"[Phoenix] annotation transport error for span {span_id}: {exc}")
                return False
        return False

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    f"{self._base_url}/healthz",
                    headers={"Authorization": f"Bearer {settings.phoenix_api_key}"},
                )
                return resp.status_code == 200
        except httpx.HTTPError:
            return False


phoenix_client = PhoenixClient()
