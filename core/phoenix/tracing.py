"""
Phoenix / OpenTelemetry tracing setup for IRIS.

Importing this module configures the Phoenix OTel exporter and instruments ADK.
It also exposes an IRIS tracer so the deterministic /event path can open its own
span per clinical event (the span that eval annotations attach to), plus a
force_flush() so we can guarantee a span is exported before we annotate it.
"""
from __future__ import annotations

import logging
import os

from openinference.instrumentation.google_adk import GoogleADKInstrumentor
from opentelemetry import trace as otel_trace
from phoenix.otel import register

from core.config import settings

# Phoenix/Gemini credentials must be in the environment before register().
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
os.environ["GOOGLE_CLOUD_PROJECT"] = settings.google_cloud_project
os.environ["GOOGLE_CLOUD_LOCATION"] = settings.google_cloud_location
os.environ["PHOENIX_API_KEY"] = settings.phoenix_api_key
os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = settings.phoenix_client_url.rstrip("/")


class _SuppressDetachNoise(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "Failed to detach context" not in record.getMessage()


logging.getLogger("opentelemetry.context").addFilter(_SuppressDetachNoise())

_tracer_provider = register(
    project_name=settings.phoenix_project_name,
    batch=True,
    set_global_tracer_provider=False,
    auto_instrument=True,
    verbose=False,
)
GoogleADKInstrumentor().instrument(tracer_provider=_tracer_provider)

_tracer = _tracer_provider.get_tracer("iris")


def get_tracer() -> otel_trace.Tracer:
    return _tracer


def get_tracer_provider():
    return _tracer_provider


def force_flush(timeout_millis: int = 5000) -> None:
    """Flush pending spans so they exist in Phoenix before we annotate them."""
    try:
        _tracer_provider.force_flush(timeout_millis)
    except Exception as exc:  # pragma: no cover - best effort
        print(f"[Tracing] force_flush failed: {exc}")
