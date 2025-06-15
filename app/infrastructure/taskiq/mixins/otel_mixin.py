import contextvars
from typing import Any

from opentelemetry import trace
from opentelemetry.propagate import inject

# Context variables to store trace information
_trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "trace_id", default="unknown"
)
_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="unknown"
)


def set_trace_context(trace_id: str, request_id: str) -> None:
    """Set trace context in current context."""
    _trace_id_var.set(trace_id)
    _request_id_var.set(request_id)


def get_current_trace_context() -> dict[str, str]:
    """Get current trace context."""
    return {"trace_id": _trace_id_var.get(), "request_id": _request_id_var.get()}


class OtelMixin:
    """Mixin to add OpenTelemetry context propagation to TaskManager."""

    async def submit_task(self, task_name: str, *args: Any, **kwargs: Any) -> str:
        """Submit task with OpenTelemetry context propagation."""

        # Get current trace context
        trace_context = get_current_trace_context()

        # Get current OpenTelemetry span context
        current_span = trace.get_current_span()
        span_context = current_span.get_span_context() if current_span else None

        # Inject OpenTelemetry context into task labels
        carrier = {}
        inject(carrier)

        # Prepare labels with trace context
        labels = kwargs.pop("labels", {})
        labels.update(
            {
                "trace_id": trace_context.get("trace_id", "unknown"),
                "request_id": trace_context.get("request_id", "unknown"),
            }
        )

        # Add OpenTelemetry context to labels
        for key, value in carrier.items():
            labels[f"otel-{key}"] = value

        # Add span context if available
        if span_context and span_context.is_valid:
            labels.update(
                {
                    "otel-trace-id": format(span_context.trace_id, "032x"),
                    "otel-span-id": format(span_context.span_id, "016x"),
                    "otel-trace-flags": format(span_context.trace_flags, "02x"),
                }
            )

        # Add labels back to kwargs
        kwargs["labels"] = labels

        # noinspection PyUnresolvedReferences
        return await super().submit_task(task_name, *args, **kwargs)
