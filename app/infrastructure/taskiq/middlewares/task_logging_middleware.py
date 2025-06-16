import time
from datetime import datetime
from typing import Any

from kink import di
from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult

from app.common.logging import get_logger
from app.common.utils import DataSanitizer, PrismaDataTransformer
from app.core.config import Configuration
from app.core.config.taskiq_config import TaskiqConfiguration
from app.infrastructure.database import Database


# noinspection PyBroadException
class TaskLoggingMiddleware(TaskiqMiddleware):
    """
    Task logging middleware that directly writes to database
    to avoid circular dependencies with task_manager.
    """

    def __init__(self, config: TaskiqConfiguration) -> None:
        super().__init__()

        self.config = config
        self.task_logging_config = di[Configuration].task_logging
        self.app_version = di[Configuration].app_version

        self.db = di[Database]
        self.logger = get_logger(__name__)

        # Tasks to exclude from logging to prevent loops
        self.excluded_tasks = self.task_logging_config.excluded_tasks

    async def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        """Log task start directly to database."""

        await Database.connect_db()

        if not self._should_log_task(message.task_name):
            return message

        # Store start time for duration calculation
        message.labels["_logging_start_time"] = time.perf_counter()
        message.labels["_logging_start_timestamp"] = datetime.now(di["timezone"])

        try:
            await self._log_task_start(message)

        except Exception as e:
            self.logger.error(f"failed to log task start: {e}")

        return message

    async def post_execute(
        self, message: TaskiqMessage, result: TaskiqResult[Any]
    ) -> None:
        """Log task completion directly to database."""

        if not self._should_log_task(message.task_name):
            return

        try:
            await self._log_task_completion(message, result)

        except Exception as e:
            self.logger.error(f"failed to log task completion: {e}")

    async def on_error(
        self, message: TaskiqMessage, result: TaskiqResult[Any], exception: Exception
    ) -> None:
        """Log task error directly to database."""

        if not self._should_log_task(message.task_name):
            return

        try:
            await self._log_task_error(message, result, exception)

        except Exception as e:
            self.logger.error(f"failed to log task error: {e}")

    def _should_log_task(self, task_name: str) -> bool:
        """Determine if task should be logged."""

        return (
            getattr(self.task_logging_config, "enabled", True)
            and task_name not in self.excluded_tasks
        )

    async def _log_task_start(self, message: TaskiqMessage) -> None:
        """Log task start to database."""

        await Database.connect_db()

        task_data = {
            "task_id": message.task_id,
            "task_name": message.task_name,
            "trace_id": self._get_trace_id(message),
            "request_id": self._get_request_id(message),
            "status": "running",
            "priority": message.labels.get("priority", "normal"),
            "queue": message.labels.get("queue", self.config.queue),
            "broker_type": self.config.broker_type.value,
            "submitted_at": datetime.now(di["timezone"]),
            "started_at": message.labels.get("_logging_start_timestamp"),
            "task_args": DataSanitizer.sanitize_data(list(message.args))
            if message.args
            else None,
            "task_kwargs": DataSanitizer.sanitize_data(dict(message.kwargs))
            if message.kwargs
            else None,
            "task_labels": self._sanitize_labels(message.labels),
            "retry_count": message.labels.get("retry_count", 0),
            "max_retries": message.labels.get(
                "max_retries", self.config.default_retry_count
            ),
            "execution_environment": "taskiq_worker",
            "worker_id": self._get_worker_id(),
            "app_version": self.app_version or "unknown",
            "logged_at": datetime.now(di["timezone"]),
        }

        prisma_data = PrismaDataTransformer.prepare_data(task_data, "TaskLog")

        await self.db.tasklog.create(data=prisma_data)

    async def _log_task_completion(
        self, message: TaskiqMessage, result: TaskiqResult[Any]
    ) -> None:
        """Log task completion to database."""

        await Database.connect_db()

        start_time = message.labels.get("_logging_start_time")
        duration_ms = None

        if start_time:
            duration_ms = (time.perf_counter() - start_time) * 1000

        update_data = {
            "status": "success" if not result.is_err else "failed",
            "completed_at": datetime.now(di["timezone"]),
            "duration_ms": round(duration_ms, 2) if duration_ms else None,
            "task_result": DataSanitizer.sanitize_data(result.return_value)
            if not result.is_err
            else None,
            "memory_usage_mb": self._get_memory_usage(),
            "error_occurred": result.is_err,
        }

        if result.is_err and result.exception:
            update_data.update(
                {
                    "task_error": str(result.exception)[:1000],
                    "error_type": type(result.exception).__name__,
                    "error_message": str(result.exception)[:500],
                    "error_category": self._categorize_error(result.exception),
                }
            )

        prisma_data = PrismaDataTransformer.prepare_data(update_data, "TaskLog")
        await self.db.tasklog.update(
            where={"task_id": message.task_id}, data=prisma_data
        )

    async def _log_task_error(
        self, message: TaskiqMessage, _result: TaskiqResult[Any], exception: Exception
    ) -> None:
        """Log task error to database."""

        await Database.connect_db()

        start_time = message.labels.get("_logging_start_time")
        duration_ms = None
        if start_time:
            duration_ms = (time.perf_counter() - start_time) * 1000

        update_data = {
            "status": "failed",
            "completed_at": datetime.now(di["timezone"]),
            "duration_ms": round(duration_ms, 2) if duration_ms else None,
            "error_occurred": True,
            "task_error": str(exception)[:1000],
            "error_type": type(exception).__name__,
            "error_message": str(exception)[:500],
            "error_category": self._categorize_error(exception),
            "memory_usage_mb": self._get_memory_usage(),
        }

        try:
            prisma_data = PrismaDataTransformer.prepare_data(update_data, "TaskLog")
            await self.db.tasklog.update(
                where={"task_id": message.task_id}, data=prisma_data
            )

        except Exception:
            # If update fails, create new record
            await self.db.tasklog.create(
                data={
                    "task_id": message.task_id,
                    "task_name": message.task_name,
                    "trace_id": self._get_trace_id(message),
                    "request_id": self._get_request_id(message),
                    "submitted_at": datetime.now(di["timezone"]),
                    **update_data,
                }
            )

    def _get_trace_id(self, message: TaskiqMessage) -> str:
        return (
            message.labels.get("trace_id", "unknown")
            if message.labels.get("trace_id", "unknown") != "unknown"
            else message.kwargs.get("trace_id", "unknown")
        )

    def _get_request_id(self, message: TaskiqMessage) -> str:
        return (
            message.labels.get("request_id", "unknown")
            if message.labels.get("request_id", "unknown") != "unknown"
            else message.kwargs.get("request_id", "unknown")
        )

    def _sanitize_labels(self, labels: dict) -> dict:
        """Sanitize task labels for logging, removing non-serializable objects."""

        if not labels:
            return {}

        sanitized = {}
        for key, value in labels.items():
            # Skip internal logging keys and non-serializable objects
            if key.startswith("_logging_") or key.startswith("_otel_"):
                continue

            # Skip span objects and other complex objects
            if hasattr(value, "__class__") and "span" in str(type(value)).lower():
                continue

            try:
                import json

                json.dumps(value)  # Test serializability
                sanitized[key] = value

            except (TypeError, ValueError):
                # Convert non-serializable objects to string representation
                sanitized[key] = str(value)[:200]

        return DataSanitizer.sanitize_data(sanitized)

    def _get_worker_id(self) -> str:
        """Get unique worker identifier."""

        import os

        return f"{os.getpid()}@{os.uname().nodename}"

    def _get_memory_usage(self) -> float:
        """Get current memory usage in MB."""

        try:
            import psutil

            process = psutil.Process()
            return round(process.memory_info().rss / 1024 / 1024, 2)
        except (ImportError, Exception):
            return 0.0

    def _categorize_error(self, exception: Exception) -> str:
        """Categorize error for analysis."""

        error_msg = str(exception).lower()

        if "connection" in error_msg or "timeout" in error_msg:
            return "connection_error"

        if "validation" in error_msg or "invalid" in error_msg:
            return "validation_error"

        if "permission" in error_msg or "unauthorized" in error_msg:
            return "permission_error"

        if "not found" in error_msg:
            return "not_found_error"

        return "unknown_error"
