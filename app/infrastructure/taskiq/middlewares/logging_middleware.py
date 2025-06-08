import time
from datetime import datetime
from typing import Any

from kink import di
from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult

from app.common.logging import get_logger
from app.common.utils import DataSanitizer
from app.infrastructure.taskiq.config import TaskiqConfiguration
from app.infrastructure.taskiq.schemas import (
    TaskExecutionMetrics,
    TaskiqMetricsCollector,
    TaskStatus,
)


class LoggingMiddleware(TaskiqMiddleware):
    """
    Simplified logging middleware focused solely on task execution logging.
    Removes overlap with error handling middleware.
    """

    def __init__(
        self,
        config: TaskiqConfiguration,
        metrics_collector: TaskiqMetricsCollector | None = None,
    ) -> None:
        super().__init__()

        self.config = config
        self.metrics_collector = metrics_collector
        self.logger = get_logger(__name__)

    def _create_execution_context(self, message: TaskiqMessage) -> dict[str, Any]:
        """Create execution context for logging."""

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

        # Add task arguments if configured
        if self.config.sanitize_logs:
            context["task_args"] = (
                DataSanitizer.sanitize_data(message.args) if message.args else None
            )
            context["task_kwargs"] = (
                DataSanitizer.sanitize_data(message.kwargs) if message.kwargs else None
            )
        else:
            context["task_args"] = list(message.args) if message.args else None
            context["task_kwargs"] = dict(message.kwargs) if message.kwargs else None

        return context

    def _get_worker_id(self) -> str:
        """Get unique worker identifier."""

        import os

        return f"{os.getpid()}@{os.uname().nodename}"

    def _get_memory_usage(self) -> float:
        """Get current memory usage in MB."""

        try:
            import psutil

            process = psutil.Process()
            return process.memory_info().rss / 1024 / 1024

        except (ImportError, AttributeError, Exception):
            return 0.0

    async def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        """Pre-execution logging."""

        context = self._create_execution_context(message)

        # Record task start metrics
        if self.metrics_collector:
            metrics = TaskExecutionMetrics(
                task_id=message.task_id,
                task_name=message.task_name,
                start_time=datetime.now(di["timezone"]),
                status=TaskStatus.RUNNING,
            )
            await self.metrics_collector.record_task_started(metrics)

        # Log task start
        self.logger.bind(**context).info(
            f"task '{message.task_name}' execution started",
            extra={
                "event": "task_started",
                "priority": message.labels.get("priority", "normal"),
                "queue": message.labels.get("queue", self.config.default_queue),
            },
        )

        # Store timing information
        message.labels["_start_time"] = time.perf_counter()
        message.labels["_start_timestamp"] = datetime.now(di["timezone"]).isoformat()

        return message

    async def post_execute(
        self, message: TaskiqMessage, result: TaskiqResult[Any]
    ) -> None:
        """Post-execution logging for successful tasks."""

        if result.is_err:
            return  # Error handling is done by error middleware

        context = self._create_execution_context(message)

        # Calculate execution metrics
        start_time = message.labels.get("_start_time")
        duration = time.perf_counter() - start_time if start_time else None

        # Update context with execution results
        context.update(
            {
                "event": "task_completed",
                "execution_status": "success",
                "is_error": False,
                "execution_duration_seconds": round(duration, 4) if duration else None,
                "memory_usage_mb": self._get_memory_usage(),
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
                status=TaskStatus.SUCCESS,
                memory_usage_mb=self._get_memory_usage(),
            )
            await self.metrics_collector.record_task_completed(metrics)

        # Add successful result information (if configured)
        if result.return_value is not None and not self.config.sanitize_logs:
            context["task_result"] = str(result.return_value)[:500]

        # Log successful completion
        self.logger.bind(**context).info(
            f"task '{message.task_name}' execution completed successfully"
        )
