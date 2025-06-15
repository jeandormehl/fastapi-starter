from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Span, Tracer

_tracer_cache = {}


def get_tracer(name: str, version: str | None = None) -> Tracer:
    """Get or create a tracer instance."""

    cache_key = f"{name}:{version or 'default'}"
    if cache_key not in _tracer_cache:
        tracer_provider = trace.get_tracer_provider()
        _tracer_cache[cache_key] = tracer_provider.get_tracer(name, version)

    return _tracer_cache[cache_key]


def create_span(name: str, tracer_name: str | None = None, **attributes: Any) -> Span:
    """Create a new span with optional attributes."""

    tracer = get_tracer(tracer_name or "application.custom")
    span = tracer.start_span(name)

    for key, value in attributes.items():
        span.set_attribute(key, value)

    return span
