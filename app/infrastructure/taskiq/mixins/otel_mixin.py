from typing import Any

from opentelemetry.propagate import inject


class OtelMixin:
    """Mixin to add otel context propagation to TaskManager."""

    async def submit_task(self, task_name: str, *args: Any, **kwargs: Any) -> str:
        """Submit task with OpenTelemetry context propagation."""

        # Get current trace context
        # TODO: GET THIS FROM COMMON MIDDLEWARE
        # trace_context = get_current_trace_context()

        # Inject OpenTelemetry context into task labels
        carrier = {}
        inject(carrier)

        # Prepare labels with trace context
        labels = kwargs.pop("labels", {})
        labels.update(
            {
                # TODO: FIX THIS AFTER MIDDLEWARE IMPLEMENTATION
                # "trace_id": trace_context.get("trace_id", ""),
                # "request_id": trace_context.get("request_id", ""),
            }
        )

        # Add OpenTelemetry context to labels
        for key, value in carrier.items():
            labels[f"otel-{key}"] = value

        # Add labels back to kwargs
        kwargs["labels"] = labels

        # noinspection PyUnresolvedReferences
        return await super().submit_task(task_name, *args, **kwargs)
