import contextlib
import time
from typing import Any

from opentelemetry import context, trace
from opentelemetry.trace import Span, Status, StatusCode
from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult

from app.common.logging import get_logger
from app.infrastructure.observability.context import extract_context_from_task
from app.infrastructure.observability.metrics import get_meter
from app.infrastructure.observability.tracing import get_tracer


class TracingMiddleware(TaskiqMiddleware):
    """TaskIQ middleware for task tracing with full OpenTelemetry integration."""

    def __init__(self) -> None:
        super().__init__()
        self.tracer = get_tracer("taskiq.worker", "1.0.0")
        self.meter = get_meter("taskiq.worker", "1.0.0")

        self.logger = get_logger(__name__)

        # Initialize metrics with error handling
        self.task_duration = None
        self.task_counter = None
        self.task_error_counter = None

        try:
            self.task_duration = self.meter.create_histogram(
                name="task_duration_seconds",
                description="Task execution duration in seconds",
                unit="s",
            )
            self.task_counter = self.meter.create_counter(
                name="task_total",
                description="Total number of tasks processed",
            )
            self.task_error_counter = self.meter.create_counter(
                name="task_error_total",
                description="Total number of task errors",
            )

        except Exception as e:
            self.logger.warning(f"failed to create task metrics: {e}")

    async def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        """Pre-execution with optimized OpenTelemetry context setup."""

        try:
            # Extract trace context from task message
            otel_context = extract_context_from_task(message)

            # Get trace IDs
            trace_id = self._get_trace_id(message)
            request_id = self._get_request_id(message)

            with context.attach(otel_context):
                # Start span for task execution
                span = self.tracer.start_span(
                    f"task.{message.task_name}", kind=trace.SpanKind.CONSUMER
                )

                # Set span attributes
                self._set_span_attributes(span, message, trace_id, request_id)

                # Store span and timing in message labels
                if not message.labels:
                    message.labels = {}

                message.labels["_otel_span"] = span
                message.labels["_otel_start_time"] = time.time()

                # Make span current for task execution
                token = context.attach(trace.set_span_in_context(span))
                message.labels["_otel_context_token"] = token

        except Exception as e:
            self.logger.warning(
                f"failed to setup tracing for task {message.task_name}: {e}"
            )

        return message

    async def post_execute(
        self, message: TaskiqMessage, result: TaskiqResult[Any]
    ) -> None:
        """Post-execution with optimized metrics and span completion."""

        span = message.labels.get("_otel_span") if message.labels else None
        start_time = message.labels.get("_otel_start_time") if message.labels else None
        context_token = (
            message.labels.get("_otel_context_token") if message.labels else None
        )

        if not span or start_time is None:
            return

        try:
            # Calculate duration
            duration_seconds = time.time() - start_time

            # Create labels for metrics
            labels = {
                "task_name": message.task_name,
                "queue": (
                    message.labels.get("queue", "default")
                    if message.labels
                    else "default"
                ),
                "status": "success" if not result.is_err else "error",
            }

            # Record metrics
            self._record_metrics(duration_seconds, labels, result.is_err)

            # Set span attributes
            span.set_attribute("task.duration_seconds", round(duration_seconds, 3))
            span.set_attribute(
                "task.status", "success" if not result.is_err else "error"
            )

            if not result.is_err:
                span.set_status(Status(StatusCode.OK))

                # Add result metadata if available
                if result.return_value is not None:
                    result_type = type(result.return_value).__name__
                    span.set_attribute("task.result.type", result_type)

                    # Add result size if it's a collection
                    with contextlib.suppress(Exception):
                        if hasattr(result.return_value, "__len__"):
                            span.set_attribute(
                                "task.result.size", len(result.return_value)
                            )

            # Handle task error
            elif result.exception:
                span.record_exception(result.exception)
                span.set_status(Status(StatusCode.ERROR, str(result.exception)[:200]))
                span.set_attribute("task.error.type", type(result.exception).__name__)

            else:
                span.set_status(Status(StatusCode.ERROR, "Task failed"))

        except Exception as e:
            self.logger.warning(
                f"failed to complete tracing for task {message.task_name}: {e}"
            )
        finally:
            # Clean up context and finish span
            self._cleanup_span_context(context_token, span)

    async def on_error(
        self,
        message: TaskiqMessage,
        result: TaskiqResult[Any],  # noqa: ARG002
        exception: Exception,
    ) -> None:
        """Handle task errors with optimized tracing."""
        span = message.labels.get("_otel_span") if message.labels else None
        start_time = message.labels.get("_otel_start_time") if message.labels else None
        context_token = (
            message.labels.get("_otel_context_token") if message.labels else None
        )

        if span:
            try:
                # Calculate duration
                duration_seconds = (time.time() - start_time) if start_time else 0

                # Record exception
                span.record_exception(exception)
                span.set_status(Status(StatusCode.ERROR, str(exception)[:200]))
                span.set_attribute("task.duration_seconds", round(duration_seconds, 3))
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

                self._record_metrics(duration_seconds, error_labels, is_error=True)

            except Exception as e:
                self.logger.warning(
                    f"failed to handle error tracing for task {message.task_name}: {e}"
                )
            finally:
                self._cleanup_span_context(context_token, span)

    def _record_metrics(
        self, duration_seconds: float, labels: dict, is_error: bool = False
    ) -> None:
        """Record metrics with error handling."""
        try:
            if self.task_duration:
                self.task_duration.record(duration_seconds, labels)
            if self.task_counter:
                self.task_counter.add(1, labels)
            if is_error and self.task_error_counter:
                self.task_error_counter.add(1, labels)
        except Exception as e:
            self.logger.debug(f"failed to record task metrics: {e}")

    # noinspection PyBroadException
    def _cleanup_span_context(self, context_token: Any, span: Span) -> None:
        """Clean up context and span with error handling."""
        try:
            if context_token:
                context.detach(context_token)
            if span:
                span.end()
        except Exception:
            contextlib.suppress(Exception)

    def _set_span_attributes(
        self, span: Span, message: TaskiqMessage, trace_id: str, request_id: str
    ) -> None:
        """Set comprehensive span attributes with error handling."""

        try:
            span.set_attribute("task.name", message.task_name)
            span.set_attribute("task.id", message.task_id)
            span.set_attribute(
                "task.queue",
                message.labels.get("queue", "default") if message.labels else "default",
            )
            span.set_attribute(
                "task.retry_count",
                message.labels.get("retry_count", 0) if message.labels else 0,
            )
            span.set_attribute("custom.trace_id", trace_id)
            span.set_attribute("custom.request_id", request_id)

            # Add task arguments (sanitized and limited)
            if message.args:
                span.set_attribute("task.args_count", len(message.args))

            if message.kwargs:
                sanitized_kwargs = self._sanitize_task_data(message.kwargs)
                for i, (key, value) in enumerate(sanitized_kwargs.items()):
                    if i >= 10:  # Limit to 10 attributes
                        break
                    span.set_attribute(f"task.kwarg.{key}", str(value)[:100])

        except Exception as e:
            self.logger.debug(f"failed to set task span attributes: {e}")

    def _get_trace_id(self, message: TaskiqMessage) -> str:
        """Extract trace ID from task message with fallbacks."""
        if message.labels and message.labels.get("trace_id", "unknown") != "unknown":
            return str(message.labels["trace_id"])

        if message.kwargs and message.kwargs.get("trace_id", "unknown") != "unknown":
            return str(message.kwargs["trace_id"])

        return "unknown"

    def _get_request_id(self, message: TaskiqMessage) -> str:
        """Extract request ID from task message with fallbacks."""
        if message.labels and message.labels.get("request_id", "unknown") != "unknown":
            return str(message.labels["request_id"])

        if message.kwargs and message.kwargs.get("request_id", "unknown") != "unknown":
            return str(message.kwargs["request_id"])

        return "unknown"

    def _sanitize_task_data(self, data: dict) -> dict:
        """Sanitize task data for tracing with improved performance."""
        sanitized = {}
        sensitive_keys = {"password", "secret", "token", "key", "auth", "credential"}

        for key, value in data.items():
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, dict | list):
                size = len(value) if hasattr(value, "__len__") else "?"
                sanitized[key] = f"[{type(value).__name__}:{size}]"
            else:
                sanitized[key] = str(value)[:50]

        return sanitized
