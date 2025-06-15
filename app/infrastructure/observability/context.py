from typing import Any

from fastapi import Request
from opentelemetry import context
from opentelemetry.propagate import extract, inject
from taskiq import TaskiqMessage


def inject_context_into_task(
    request: Request, task_kwargs: dict[str, Any]
) -> dict[str, Any]:
    """Inject OpenTelemetry context into task kwargs for proper propagation."""

    try:
        # Get current context
        current_context = getattr(request.state, "otel_context", context.get_current())

        # Create carrier for context injection
        carrier = {}

        # Inject context into carrier
        with context.attach(current_context):
            inject(carrier)

        # Add context to task kwargs with otel- prefix for labels
        for key, value in carrier.items():
            task_kwargs[f"otel-{key}"] = value

        # Also add trace and request IDs
        if hasattr(request.state, "trace_id"):
            task_kwargs["trace_id"] = request.state.trace_id
        if hasattr(request.state, "request_id"):
            task_kwargs["request_id"] = request.state.request_id

    except Exception as e:
        # Log error but don't fail the task
        print(f"failed to inject context into task: {e}")

    return task_kwargs


def extract_context_from_task(message: TaskiqMessage) -> Any:
    """Extract OpenTelemetry context from task message."""

    try:
        carrier = {}

        # Extract context from labels
        if message.labels:
            for key, value in message.labels.items():
                if key.startswith("otel-"):
                    carrier[key[5:]] = value  # Remove 'otel-' prefix

        # Extract context from kwargs
        if message.kwargs:
            for key, value in message.kwargs.items():
                if key.startswith("otel-"):
                    carrier[key[5:]] = value

        # Extract OpenTelemetry context
        return extract(carrier) if carrier else context.get_current()

    except Exception as e:
        print(f"failed to extract context from task: {e}")
        return context.get_current()
