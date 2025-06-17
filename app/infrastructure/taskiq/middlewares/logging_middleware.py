import time
from datetime import datetime
from typing import Any

from kink import di
from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult

from app.common.logging import get_logger
from app.common.utils import DataSanitizer, ScopeNormalizer
from app.core.config.taskiq_config import TaskiqConfiguration


class LoggingMiddleware(TaskiqMiddleware):
    """
    Simplified logging middleware focused solely on task execution logging.
    Removes overlap with error handling middleware.
    """

    def __init__(
        self,
        config: TaskiqConfiguration,
    ) -> None:
        super().__init__()

        self.config = config
        self.logger = get_logger(__name__)

    def _create_comprehensive_task_context(
        self, message: TaskiqMessage, result: TaskiqResult = None
    ) -> dict[str, Any]:
        """Create comprehensive task context with all relevant TaskIQ data."""

        trace_id = (
            message.labels.get("trace_id")
            if message.labels.get("trace_id", "unknown") != "unknown"
            else message.kwargs.get("trace_id", "unknown")
        )
        request_id = (
            message.labels.get("request_id")
            if message.labels.get("request_id", "unknown") != "unknown"
            else message.kwargs.get("request_id", "unknown")
        )

        task_labels = {}

        if message.labels:
            for key, value in message.labels.items():
                if key not in [
                    "_start_time",
                    "_end_time",
                ]:  # Exclude internal timing
                    try:
                        # Ensure serializable
                        import json

                        json.dumps(value)
                        task_labels[key] = value
                    except (TypeError, ValueError):
                        task_labels[key] = str(value)

        task_kwargs = {}
        if message.kwargs:
            if self.config.sanitize_logs:
                task_kwargs = DataSanitizer.sanitize_data(message.kwargs)
            else:
                for key, value in message.kwargs.items():
                    try:
                        import json

                        json.dumps(value)
                        task_kwargs[key] = value
                    except (TypeError, ValueError):
                        task_kwargs[key] = str(value)

        context = {
            "trace_id": str(trace_id),
            "request_id": str(request_id),
            "task_id": message.task_id,
            "task_name": message.task_name,
            "task_labels": task_labels,
            "task_args": (
                self._sanitize_task_args(list(message.args)) if message.args else []
            ),
            "task_kwargs": task_kwargs,
            "execution_environment": "taskiq_worker",
            "timestamp": datetime.now(di["timezone"]).isoformat(),
            "worker_id": self._get_worker_id(),
            "broker_type": self.config.broker_type.value,
            "queue": message.labels.get("queue", self.config.queue),
            "priority": message.labels.get("priority", "normal"),
            "retry_count": message.labels.get("retry_count", 0),
            "max_retries": message.labels.get(
                "max_retries", self.config.default_retry_count
            ),
            "task_timeout": self.config.task_timeout,
            "memory_usage_mb": self._get_memory_usage(),
        }

        if result:
            context.update(
                {
                    "task_status": "success" if result.is_success else "failed",
                    "task_result": str(result.return_value)
                    if result.is_success
                    else None,
                    "task_error": str(result.exception)
                    if not result.is_success
                    else None,
                }
            )

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

        context = self._create_comprehensive_task_context(message)

        # Log task start
        self.logger.bind(**context).info(
            f"task '{message.task_name}' execution started",
            extra={
                "event": "task_started",
                "priority": message.labels.get("priority", "normal"),
                "queue": message.labels.get("queue", self.config.queue),
            },
        )

        # Store timing information
        message.labels["_start_time"] = time.perf_counter()
        message.labels["_start_timestamp"] = datetime.now(di["timezone"]).isoformat()

        return message

    # noinspection PyBroadException
    async def post_execute(
        self, message: TaskiqMessage, result: TaskiqResult[Any]
    ) -> None:
        """Post-execution logging for successful tasks."""

        if result.is_err:
            return  # Error handling is done by error middleware

        context = self._create_comprehensive_task_context(message)

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

        # Include task result in the context if available
        if result.return_value is not None:
            context["task_result"] = DataSanitizer.sanitize_data(result.return_value)
        else:
            try:
                context["task_result"] = str(result.return_value)[:500]

            except Exception:
                context["task_result"] = "[Result conversion error]"

        # Log successful completion
        self.logger.bind(**context).info(
            f"task '{message.task_name}' execution completed successfully"
        )

    # noinspection DuplicatedCode
    def _sanitize_task_args(self, args: tuple) -> dict[str, Any] | None:
        """Sanitize task arguments with special handling for scope fields."""

        if not args:
            return None

        sanitized_args = DataSanitizer.sanitize_data(list(args))

        # Post-process to normalize scope fields
        if isinstance(sanitized_args, dict):
            for key, value in sanitized_args.items():
                if "scope" in key.lower():
                    sanitized_args[key] = ScopeNormalizer.normalize_scopes(value)
        elif isinstance(sanitized_args, list):
            for _i, arg in enumerate(sanitized_args):
                if isinstance(arg, dict):
                    for key, value in arg.items():
                        if "scope" in key.lower():
                            arg[key] = ScopeNormalizer.normalize_scopes(value)

        return sanitized_args
