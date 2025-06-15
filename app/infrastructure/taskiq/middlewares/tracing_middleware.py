import contextlib
import time
from typing import Any

from opentelemetry import context, trace
from opentelemetry.propagate import extract
from opentelemetry.trace import Status, StatusCode
from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult

from app.infrastructure.observability.metrics import get_meter
from app.infrastructure.observability.tracing import get_tracer


class TracingMiddleware(TaskiqMiddleware):
    """
    Taskiq middleware for task tracing with full OpenTelemetry integration.
    Provides proper context propagation between FastAPI and Taskiq workers.
    """

    # noinspection PyBroadException
    def __init__(self) -> None:
        super().__init__()

        self.tracer = get_tracer("taskiq.worker")
        self.meter = get_meter("taskiq.worker")

        # Create metrics with error handling
        try:
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

        except Exception:
            # Gracefully handle metric creation failures
            self.task_duration = None
            self.task_counter = None
            self.task_error_counter = None
            self.task_retry_counter = None

    async def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        """Pre-execution with OpenTelemetry context setup."""

        try:
            # Extract trace context from task message labels
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
                span.set_attribute(
                    "task.queue",
                    message.labels.get("queue", "default")
                    if message.labels
                    else "default",
                )
                span.set_attribute(
                    "task.retry_count",
                    message.labels.get("retry_count", 0) if message.labels else 0,
                )
                span.set_attribute("custom.trace_id", trace_id)
                span.set_attribute("custom.request_id", request_id)

                # Add task arguments (sanitized)
                if message.args:
                    span.set_attribute("task.args_count", len(message.args))

                if message.kwargs:
                    sanitized_kwargs = self._sanitize_task_data(message.kwargs)
                    for key, value in sanitized_kwargs.items():
                        span.set_attribute(f"task.kwarg.{key}", str(value)[:100])

                # Store span and context in message for post-processing
                if not message.labels:
                    message.labels = {}

                message.labels["_otel_span"] = span
                message.labels["_otel_start_time"] = time.time()

                # Make span current for task execution
                token = context.attach(trace.set_span_in_context(span))
                message.labels["_otel_context_token"] = token

        except Exception as e:
            # Log error but don't fail the task
            print(f"failed to setup tracing for task {message.task_name}: {e}")

        return message

    # noinspection PyBroadException
    async def post_execute(  # noqa: PLR0912
        self, message: TaskiqMessage, result: TaskiqResult[Any]
    ) -> None:
        """Post-execution with metrics and span completion."""

        span = message.labels.get("_otel_span") if message.labels else None
        start_time = message.labels.get("_otel_start_time") if message.labels else None
        context_token = (
            message.labels.get("_otel_context_token") if message.labels else None
        )

        if not span or not start_time:
            return

        try:
            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Create labels for metrics
            labels = {
                "task_name": message.task_name,
                "queue": (
                    message.labels.get("queue", "default")
                    if message.labels
                    else "default"
                ),
                "status": "success" if result.is_success else "error",
            }

            # Record metrics
            if self.task_duration:
                self.task_duration.record(duration_ms, labels)

            if self.task_counter:
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
                        with contextlib.suppress(Exception):
                            span.set_attribute(
                                "task.result.size", len(result.return_value)
                            )

            else:
                # Handle task error
                if self.task_error_counter:
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
            retry_count = message.labels.get("retry_count", 0) if message.labels else 0
            if retry_count > 0 and self.task_retry_counter:
                retry_labels = {**labels, "retry_count": retry_count}
                self.task_retry_counter.add(1, retry_labels)

        except Exception as e:
            print(f"failed to complete tracing for task {message.task_name}: {e}")

        finally:
            # Clean up context and finish span
            try:
                if context_token:
                    context.detach(context_token)
                span.end()

            except Exception:
                contextlib.suppress(Exception)

    # noinspection PyBroadException
    async def on_error(
        self,
        message: TaskiqMessage,
        result: TaskiqResult[Any],  # noqa: ARG002
        exception: Exception,
    ) -> None:
        """Handle task errors with proper tracing."""

        span = message.labels.get("_otel_span") if message.labels else None
        start_time = message.labels.get("_otel_start_time") if message.labels else None
        context_token = (
            message.labels.get("_otel_context_token") if message.labels else None
        )

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
                    "queue": message.labels.get("queue", "default")
                    if message.labels
                    else "default",
                    "status": "error",
                    "error_type": type(exception).__name__,
                }

                if start_time and self.task_duration:
                    self.task_duration.record(duration_ms, error_labels)
                if self.task_error_counter:
                    self.task_error_counter.add(1, error_labels)

            except Exception:
                contextlib.suppress(Exception)

            finally:
                # Clean up context and finish span
                try:
                    if context_token:
                        context.detach(context_token)
                    span.end()

                except Exception:
                    contextlib.suppress(Exception)

    def _get_trace_id(self, message: TaskiqMessage) -> str:
        """Extract trace ID from task message."""
        if message.labels and message.labels.get("trace_id") != "unknown":
            return message.labels.get("trace_id", "unknown")

        if message.kwargs and message.kwargs.get("trace_id") != "unknown":
            return message.kwargs.get("trace_id", "unknown")

        return "unknown"

    def _get_request_id(self, message: TaskiqMessage) -> str:
        """Extract request ID from task message."""
        if message.labels and message.labels.get("request_id") != "unknown":
            return message.labels.get("request_id", "unknown")

        if message.kwargs and message.kwargs.get("request_id") != "unknown":
            return message.kwargs.get("request_id", "unknown")

        return "unknown"

    def _sanitize_task_data(self, data: dict) -> dict:
        """Sanitize task data for tracing."""
        sanitized = {}
        sensitive_keys = {"password", "secret", "token", "key", "auth", "credential"}

        for key, value in data.items():
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, dict | list):
                sanitized[key] = (
                    f"[{type(value).__name__}:"
                    f"{len(value) if hasattr(value, '__len__') else '?'}]"
                )
            else:
                sanitized[key] = str(value)[:50]  # Limit length

        return sanitized
