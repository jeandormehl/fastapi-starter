import time
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from kink import di
from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult

from app.core.logging import get_logger
from app.infrastructure.taskiq.config import TaskiqConfiguration
from app.infrastructure.taskiq.schemas import (
    TaskExecutionMetrics,
    TaskiqMetricsCollector,
    TaskStatus,
)


class LoggingMiddleware(TaskiqMiddleware):
    """Logging middleware with comprehensive monitoring."""

    def __init__(
        self,
        config: TaskiqConfiguration,
        metrics_collector: TaskiqMetricsCollector | None = None,
    ) -> None:
        super().__init__()

        self.config = config
        self.metrics_collector = metrics_collector
        self.logger = get_logger(__name__)

        # Performance tracking
        self.execution_context: dict[str, Any] = {}

    def _create_execution_context(self, message: TaskiqMessage) -> dict[str, Any]:
        """Create comprehensive execution context."""

        context = {
            "task_id": message.task_id,
            "task_name": message.task_name,
            "task_labels": dict(message.labels) if message.labels else {},
            "execution_environment": "taskiq_worker",
            "trace_id": message.kwargs.get("trace_id"),
            "request_id": message.kwargs.get("request_id"),
            "timestamp": datetime.now(di["timezone"]).isoformat(),
            "worker_id": self._get_worker_id(),
            "broker_type": self.config.broker_type.value,
        }

        # Add task arguments if logging is enabled
        if self.config.sanitize_logs:
            context["task_args"] = (
                self._sanitize_data(message.args) if message.args else None
            )
            context["task_kwargs"] = (
                self._sanitize_data(message.kwargs) if message.kwargs else None
            )

        else:
            context["task_args"] = list(message.args) if message.args else None
            context["task_kwargs"] = dict(message.kwargs) if message.kwargs else None

        return context

    def _sanitize_data(self, data: Any) -> Any:
        """Data sanitization."""

        sensitive_patterns = {
            "password",
            "token",
            "secret",
            "key",
            "auth",
            "credential",
            "pwd",
            "pass",
            "api_key",
            "access_token",
            "refresh_token",
        }

        if isinstance(data, dict):
            return {
                key: "[REDACTED]"
                if any(pattern in key.lower() for pattern in sensitive_patterns)
                else self._sanitize_data(value)
                for key, value in data.items()
            }

        if isinstance(data, list | tuple):
            return [self._sanitize_data(item) for item in data]

        if isinstance(data, str) and len(data) > 1000:
            return data[:1000] + "...[TRUNCATED]"

        return data

    def _get_worker_id(self) -> str:
        """Get unique worker identifier."""

        import os

        return f"{os.getpid()}@{os.uname().nodename}"

    @contextmanager
    def _performance_tracking(self, task_id: str) -> Any:
        """Context manager for performance tracking."""

        start_time = time.perf_counter()
        start_memory = self._get_memory_usage()

        try:
            yield

        finally:
            end_time = time.perf_counter()
            end_memory = self._get_memory_usage()

            self.execution_context[task_id] = {
                "execution_time": end_time - start_time,
                "memory_delta": end_memory - start_memory,
                "start_memory": start_memory,
                "end_memory": end_memory,
            }

    def _get_memory_usage(self) -> float:
        """Get current memory usage in MB."""

        try:
            import psutil

            process = psutil.Process()

            try:
                return process.memory_info().rss / 1024 / 1024

            except (AttributeError, psutil.Error) as e:
                self.logger.debug(f"failed to get memory info: {e}")
                return 0.0

        except ImportError:
            return 0.0

        except Exception as e:
            self.logger.debug(f"unexpected error getting memory usage: {e}")
            return 0.0

    async def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        """Pre-execution logging with metrics."""

        context = self._create_execution_context(message)

        # Create execution metrics
        if self.metrics_collector:
            metrics = TaskExecutionMetrics(
                task_id=message.task_id,
                task_name=message.task_name,
                start_time=datetime.now(di["timezone"]),
                status=TaskStatus.RUNNING,
            )
            await self.metrics_collector.record_task_started(metrics)

        # Log task start with context
        self.logger.bind(**context).info(
            f"task '{message.task_name}' execution started",
            extra={
                "event": "task_started",
                "priority": message.labels.get("priority", "normal"),
                "queue": message.labels.get("queue", self.config.default_queue),
            },
        )

        # Store start time for duration calculation
        message.labels["_start_time"] = time.perf_counter()
        message.labels["_start_timestamp"] = datetime.now(di["timezone"]).isoformat()

        return message

    async def post_execute(
        self, message: TaskiqMessage, result: TaskiqResult[Any]
    ) -> None:
        """Post-execution logging with comprehensive metrics."""

        context = self._create_execution_context(message)

        # Calculate execution metrics
        start_time = message.labels.get("_start_time")
        duration = time.perf_counter() - start_time if start_time else None

        # Get performance context
        perf_context = self.execution_context.get(message.task_id, {})

        # Update context with execution results
        context.update(
            {
                "event": "task_completed",
                "execution_status": "failed" if result.is_err else "success",
                "is_error": result.is_err,
                "execution_duration_seconds": round(duration, 4) if duration else None,
                "memory_usage_mb": perf_context.get("end_memory"),
                "memory_delta_mb": perf_context.get("memory_delta"),
            }
        )

        # Record completion metrics
        if self.metrics_collector:
            metrics = TaskExecutionMetrics(
                task_id=message.task_id,
                task_name=message.task_name,
                start_time=datetime.fromisoformat(
                    message.labels.get("_start_timestamp")
                )
                if message.labels.get("_start_timestamp")
                else datetime.now(di["timezone"]),
                end_time=datetime.now(di["timezone"]),
                duration_seconds=duration,
                status=TaskStatus.FAILED if result.is_err else TaskStatus.SUCCESS,
                memory_usage_mb=perf_context.get("end_memory"),
            )

            if result.is_err:
                # Extract error information
                msg = "unknown error"
                error = Exception(result.log) if result.log else Exception(msg)

                await self.metrics_collector.record_task_failed(metrics, error)

            else:
                await self.metrics_collector.record_task_completed(metrics)

        # Log result
        if result.is_err:
            context.update(
                {
                    "error_log": result.log,
                    "error_type": "task_execution_error",
                }
            )

            # Add result value if it contains error information
            if result.return_value:
                context["error_details"] = str(result.return_value)[:500]

            self.logger.bind(**context).error(
                f"task '{message.task_name}' execution failed: {result.log}"
            )

        else:
            # Add successful result information
            if result.return_value is not None and not self.config.sanitize_logs:
                context["task_result"] = str(result.return_value)[:500]

            self.logger.bind(**context).info(
                f"task '{message.task_name}' execution completed successfully"
            )

        # Cleanup execution context
        self.execution_context.pop(message.task_id, None)

    async def on_error(
        self, message: TaskiqMessage, _result: TaskiqResult[Any], exception: Exception
    ) -> None:
        """Error logging with detailed context."""
        context = self._create_execution_context(message)

        # Calculate execution metrics
        start_time = message.labels.get("_start_time")
        duration = time.perf_counter() - start_time if start_time else None

        context.update(
            {
                "event": "task_error",
                "execution_status": "error",
                "exception_type": type(exception).__name__,
                "exception_message": str(exception),
                "exception_module": getattr(
                    exception.__class__, "__module__", "unknown"
                ),
                "execution_duration_seconds": round(duration, 4) if duration else None,
            }
        )

        # Record error metrics
        if self.metrics_collector:
            metrics = TaskExecutionMetrics(
                task_id=message.task_id,
                task_name=message.task_name,
                start_time=datetime.fromisoformat(
                    message.labels.get("_start_timestamp")
                ),
                end_time=datetime.now(di["timezone"]),
                duration_seconds=duration,
                status=TaskStatus.FAILED,
            )

            await self.metrics_collector.record_task_failed(metrics, exception)

        # Log error with full context
        self.logger.bind(**context).error(
            f"task '{message.task_name}' raised exception: {exception}",
            exc_info=exception,
        )

        # Cleanup execution context
        self.execution_context.pop(message.task_id, None)
