import contextlib
from typing import Any

from fastapi import Request
from opentelemetry import context, trace
from opentelemetry.propagate import extract, inject
from taskiq import TaskiqMessage

from app.common.logging import get_logger


def inject_context_into_task(
    request: Request, task_kwargs: dict[str, Any]
) -> dict[str, Any]:
    """Inject OpenTelemetry context into task kwargs for proper propagation."""
    try:
        # Get current context from request state or global context
        current_context = getattr(request.state, "otel_context", context.get_current())

        # Create carrier for context injection
        carrier = {}

        context_token = context.attach(current_context)
        try:
            inject(carrier)

        finally:
            context.detach(context_token)

        # Add context to task kwargs with otel- prefix
        for key, value in carrier.items():
            task_kwargs[f"otel-{key}"] = value

        # Add trace and request IDs directly for easier access
        if hasattr(request.state, "trace_id"):
            task_kwargs["trace_id"] = request.state.trace_id
        if hasattr(request.state, "request_id"):
            task_kwargs["request_id"] = request.state.request_id

    except Exception as e:
        get_logger(__name__).warning(f"failed to inject context into task: {e}")

    return task_kwargs


def extract_context_from_task(message: TaskiqMessage) -> Any:
    """Extract OpenTelemetry context from task message with improved error handling."""

    try:
        carrier = _extract_carrier_from_message(message)
        return extract(carrier) if carrier else context.get_current()
    except Exception as e:
        get_logger(__name__).warning(f"failed to extract context from task: {e}")

        return context.get_current()


def _extract_carrier_from_message(message: TaskiqMessage) -> dict[str, str]:
    """Extract OTEL carrier from task message (centralized logic)."""

    carrier = {}

    # Extract from labels first (preferred)
    if message.labels:
        for key, value in message.labels.items():
            if key.startswith("otel-"):
                carrier[key[5:]] = str(value)  # Remove 'otel-' prefix

    # Fallback to kwargs if no context in labels
    if not carrier and message.kwargs:
        for key, value in message.kwargs.items():
            if key.startswith("otel-"):
                carrier[key[5:]] = str(value)

    return carrier


# noinspection PyBroadException
def get_current_trace_info(request: Request | None = None) -> dict[str, str]:
    """Get current trace information with improved caching."""
    trace_info = {"trace_id": "unknown", "request_id": "unknown"}

    # Try to get from request state first
    if request and hasattr(request, "state"):
        trace_info["trace_id"] = getattr(request.state, "trace_id", "unknown")
        trace_info["request_id"] = getattr(request.state, "request_id", "unknown")

        if trace_info["trace_id"] != "unknown":
            return trace_info

    # Fallback to current span context
    try:
        current_span = trace.get_current_span()
        if current_span and current_span.is_recording():
            span_context = current_span.get_span_context()
            if span_context.is_valid:
                trace_info["trace_id"] = format(span_context.trace_id, "032x")

    except Exception:
        contextlib.suppress(Exception)

    return trace_info
