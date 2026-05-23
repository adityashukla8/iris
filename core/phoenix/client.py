"""
Phoenix observability client for IRIS eval results.

Primary path  — OTel span attributes (always works, no REST needed):
  Eval results are written as attributes on the current ADK span so they
  appear natively in the Phoenix trace viewer.

Secondary path — REST /v1/span_annotations (requires span to exist first):
  Attempted after the OTel write. Logged but never fatal if it fails.
"""
from __future__ import annotations

import httpx
from opentelemetry import trace as otel_trace

from core.config import settings
from sdk.models import EvalResult, IrisEvent


def _get_current_span() -> otel_trace.Span | None:
    span = otel_trace.get_current_span()
    ctx = span.get_span_context()
    return span if (ctx and ctx.is_valid) else None


def _current_span_id_hex() -> str | None:
    span = _get_current_span()
    if span:
        return format(span.get_span_context().span_id, "016x")
    return None


def record_eval_on_span(event: IrisEvent, result: EvalResult) -> None:
    """
    Write eval result as attributes on the current OTel span.
    Phoenix renders these in the trace viewer under the span's attributes.
    This works regardless of whether the REST annotation API is available.
    """
    import json
    span = _get_current_span()
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
    span.set_attribute("iris.agent_name", event.agent_name)
    span.set_attribute("iris.query_type", str(event.query_type))
    span.set_attribute("iris.trace_id", event.trace_id)


class PhoenixClient:
    def __init__(self) -> None:
        self._base_url = settings.phoenix_client_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {settings.phoenix_api_key}",
            "Content-Type": "application/json",
        }

    async def annotate_span(self, event: IrisEvent, result: EvalResult) -> bool:
        """
        Write eval result via two paths:
        1. OTel span attributes (primary — always fires when inside an ADK span)
        2. Phoenix REST /v1/span_annotations (secondary — best-effort)
        """
        # Primary: OTel attributes on the current span
        record_eval_on_span(event, result)

        # Secondary: REST annotation (requires span already in Phoenix)
        span_id = _current_span_id_hex() or event.trace_id
        payload = {
            "data": [
                {
                    "span_id": span_id,
                    "name": result.evaluator,
                    "annotator_kind": "LLM" if result.metadata.get("llm_judged") else "CODE",
                    "result": {
                        "label": result.severity.value.upper(),
                        "score": round(result.score / 10.0, 3),
                        "explanation": result.rationale,
                    },
                    "metadata": {
                        "agent_name": event.agent_name,
                        "query_type": str(event.query_type),
                        "iris_trace_id": event.trace_id,
                        "passed": result.passed,
                        "flagged_claims": result.flagged_claims,
                        "confidence": result.confidence,
                        "reasoning_chain": result.reasoning_chain,
                        **result.metadata,
                    },
                }
            ]
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self._base_url}/v1/span_annotations",
                    json=payload,
                    headers=self._headers,
                )
                resp.raise_for_status()
                return True
        except httpx.HTTPStatusError as exc:
            # Log once at debug level — not an error, OTel path already succeeded
            if exc.response.status_code != 401:
                print(f"[Phoenix] annotation {exc.response.status_code} for span {span_id}: {exc.response.text[:150]}")
            return False
        except httpx.HTTPError:
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
