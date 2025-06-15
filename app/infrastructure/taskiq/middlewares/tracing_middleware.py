import contextlib
import time
from typing import Any

from opentelemetry import context, trace
from opentelemetry.propagate import extract
from opentelemetry.trace import Status, StatusCode
from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult

from app.infrastructure.observability import get_meter, get_tracer


class TracingMiddleware(TaskiqMiddleware):
    """otel middleware for TaskiQ with comprehensive tracing and metrics."""

    def __init__(self) -> None:
        super().__init__()

        self.tracer = get_tracer("taskiq.worker")
        self.meter = get_meter("taskiq.worker")

        # Create metrics
        self.task_duration = self.meter.create_histogram(
            name="task_duration_ms",
            description="Task execution duration in milliseconds",
            unit="ms",
        )

        self.task_counter = self.meter.create_counter(
            name="task_total", description="Total number of tasks processed"
        )

        self.task_error_counter = self.meter.create_counter(
            name="task_error_total", description="Total number of task errors"
        )

        self.task_retry_counter = self.meter.create_counter(
            name="task_retry_total", description="Total number of task retries"
        )

    async def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        """Pre-execution with OpenTelemetry context setup."""

        # Extract trace context from task message
        carrier = {}
        if message.labels:
            for key, value in message.labels.items():
                if key.startswith("otel-"):
                    carrier[key[5:]] = value  # Remove 'otel-' prefix

        # Extract OpenTelemetry context
        otel_context = extract(carrier) if carrier else context.get_current()

        # Get trace IDs
        trace_id = self._get_trace_id(message)
        request_id = self._get_request_id(message)

        with context.attach(otel_context):
            # Start span for task execution
            span = self.tracer.start_span(
                f"task.{message.task_name}", kind=trace.SpanKind.CONSUMER
            )

            # Set span attributes
            span.set_attribute("task.name", message.task_name)
            span.set_attribute("task.id", message.task_id)
            span.set_attribute("task.queue", message.labels.get("queue", "default"))
            span.set_attribute("task.retry_count", message.labels.get("retry_count", 0))
            span.set_attribute("custom.trace_id", trace_id)
            span.set_attribute("custom.request_id", request_id)

            # Add task arguments (sanitized)
            if message.args:
                span.set_attribute("task.args_count", len(message.args))

            if message.kwargs:
                sanitized_kwargs = self._sanitize_task_data(message.kwargs)
                for key, value in sanitized_kwargs.items():
                    span.set_attribute(f"task.kwarg.{key}", str(value)[:100])

            # Store span in message for post-processing
            message.labels["_otel_span"] = span
            message.labels["_otel_start_time"] = time.time()

            # Make span current for task execution
            token = context.attach(trace.set_span_in_context(span))
            message.labels["_otel_context_token"] = token

        return message

    async def post_execute(
        self, message: TaskiqMessage, result: TaskiqResult[Any]
    ) -> None:
        """Post-execution with metrics and span completion."""

        span = message.labels.get("_otel_span")
        start_time = message.labels.get("_otel_start_time")
        context_token = message.labels.get("_otel_context_token")

        if not span or not start_time:
            return

        try:
            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Create labels for metrics
            labels = {
                "task_name": message.task_name,
                "queue": message.labels.get("queue", "default"),
                "status": "success" if result.is_success else "error",
            }

            # Record metrics
            self.task_duration.record(duration_ms, labels)
            self.task_counter.add(1, labels)

            # Set span attributes
            span.set_attribute("task.duration_ms", round(duration_ms, 2))
            span.set_attribute(
                "task.status", "success" if result.is_success else "error"
            )

            if result.is_success:
                # Handle successful task
                span.set_status(Status(StatusCode.OK))

                # Add result metadata if available
                if result.return_value is not None:
                    result_type = type(result.return_value).__name__
                    span.set_attribute("task.result.type", result_type)

                    # Add result size if it's a collection
                    if hasattr(result.return_value, "__len__"):
                        # noinspection PyBroadException
                        try:
                            span.set_attribute(
                                "task.result.size", len(result.return_value)
                            )
                        except Exception:
                            contextlib.suppress(Exception)

            else:
                # Handle task error
                self.task_error_counter.add(1, labels)

                if result.exception:
                    span.record_exception(result.exception)
                    span.set_status(Status(StatusCode.ERROR, str(result.exception)))
                    span.set_attribute(
                        "task.error.type", type(result.exception).__name__
                    )
                else:
                    span.set_status(Status(StatusCode.ERROR, "Task failed"))

            # Record retry if applicable
            retry_count = message.labels.get("retry_count", 0)
            if retry_count > 0:
                retry_labels = {**labels, "retry_count": retry_count}
                self.task_retry_counter.add(1, retry_labels)

        finally:
            # Clean up context and finish span
            if context_token:
                context.detach(context_token)
            span.end()

    async def on_error(
        self,
        message: TaskiqMessage,
        result: TaskiqResult[Any],  # noqa: ARG002
        exception: Exception,
    ) -> None:
        """Handle task errors with proper tracing."""

        span = message.labels.get("_otel_span")
        start_time = message.labels.get("_otel_start_time")
        context_token = message.labels.get("_otel_context_token")

        if span:
            try:
                # Calculate duration
                duration_ms = (time.time() - start_time) * 1000 if start_time else 0

                # Record exception
                span.record_exception(exception)
                span.set_status(Status(StatusCode.ERROR, str(exception)))
                span.set_attribute("task.duration_ms", round(duration_ms, 2))
                span.set_attribute("task.error.type", type(exception).__name__)
                span.set_attribute("task.status", "error")

                # Record error metrics
                error_labels = {
                    "task_name": message.task_name,
                    "queue": message.labels.get("queue", "default"),
                    "status": "error",
                    "error_type": type(exception).__name__,
                }

                if start_time:
                    self.task_duration.record(duration_ms, error_labels)
                self.task_error_counter.add(1, error_labels)

            finally:
                # Clean up context and finish span
                if context_token:
                    context.detach(context_token)
                span.end()

    def _get_trace_id(self, message: TaskiqMessage) -> str:
        """Extract trace ID from task message."""
        return (
            message.labels.get("trace_id", "unknown")
            if message.labels and message.labels.get("trace_id", "unknown") != "unknown"
            else message.kwargs.get("trace_id", "unknown")
        )

    def _get_request_id(self, message: TaskiqMessage) -> str:
        """Extract request ID from task message."""
        return (
            message.labels.get("request_id", "unknown")
            if message.labels
            and message.labels.get("request_id", "unknown") != "unknown"
            else message.kwargs.get("request_id", "unknown")
        )

    def _sanitize_task_data(self, data: dict) -> dict:
        """Sanitize task data for tracing."""
        sanitized = {}
        sensitive_keys = {"password", "secret", "token", "key", "auth", "credential"}

        for key, value in data.items():
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, dict | list):
                sanitized[key] = f"[{type(value).__name__}:{
                    len(value) if hasattr(value, '__len__') else '?'
                }]"
            else:
                sanitized[key] = str(value)[:50]  # Limit length

        return sanitized
