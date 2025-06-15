from collections import OrderedDict
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Span, Tracer

# LRU cache for tracers with size limit
_tracer_cache: OrderedDict[str, Tracer] = OrderedDict()
_MAX_CACHE_SIZE = 100


def get_tracer(name: str, version: str | None = None) -> Tracer:
    """Get or create a tracer instance with LRU caching."""
    cache_key = f"{name}:{version or 'default'}"

    if cache_key in _tracer_cache:
        # Move to end (most recently used)
        _tracer_cache.move_to_end(cache_key)
        return _tracer_cache[cache_key]

    # Create new tracer
    tracer_provider = trace.get_tracer_provider()
    tracer = tracer_provider.get_tracer(name, version)

    # Add to cache and manage size
    _tracer_cache[cache_key] = tracer
    if len(_tracer_cache) > _MAX_CACHE_SIZE:
        _tracer_cache.popitem(last=False)  # Remove oldest

    return tracer


# noinspection PyBroadException
def create_span(name: str, tracer_name: str | None = None, **attributes: Any) -> Span:
    """Create a new span with optional attributes and improved error handling."""
    try:
        tracer = get_tracer(tracer_name or "application.custom")
        span = tracer.start_span(name)

        for key, value in attributes.items():
            try:
                # Ensure attribute value is valid
                if value is not None:
                    span.set_attribute(key, str(value)[:200])  # Limit attribute length
            except Exception:  # nosec
                continue  # Skip invalid attributes

        return span
    except Exception:
        # Return a no-op span if creation fails
        return trace.NonRecordingSpan(trace.INVALID_SPAN_CONTEXT)
