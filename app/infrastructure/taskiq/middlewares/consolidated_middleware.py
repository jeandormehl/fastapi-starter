import time
from datetime import datetime
from typing import Any

from kink import di
from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult

from app.common.logging import get_logger
from app.common.utils import DataSanitizer, PrismaDataTransformer, ScopeNormalizer
from app.core.config import Configuration
from app.core.config.taskiq_config import TaskiqConfiguration
from app.infrastructure.database import Database
from app.infrastructure.taskiq.middlewares.error_middleware import ErrorMiddleware


# noinspection PyBroadException
class ConsolidatedTaskMiddleware(TaskiqMiddleware):
    def __init__(self, config: TaskiqConfiguration) -> None:
        super().__init__()

        self.config = config
        self.task_logging_config = di[Configuration].task_logging
        self.app_version = di[Configuration].app_version

        self.db = di[Database]
        self.logger = get_logger(__name__)

        # Initialize error middleware for advanced error handling
        self.error_middleware = ErrorMiddleware(config)

        # Tasks to exclude from logging to prevent loops
        self.excluded_tasks = self.task_logging_config.excluded_tasks

    async def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        """Consolidated pre-execution handling."""

        # Let error middleware handle circuit breaker and quarantine checks
        message = await self.error_middleware.pre_execute(message)

        # Add logging and database persistence
        await Database.connect_db()

        if self._should_log_task(message.task_name):
            # Store timing information
            message.labels["_start_time"] = time.perf_counter()
            message.labels["_start_timestamp"] = datetime.now(di["timezone"])

            # Create comprehensive context
            context = self._create_task_context(message)

            # Log task start
            self.logger.bind(**context).info(
                f"task '{message.task_name}' execution started",
                extra={"event": "task_started"},
            )

            # Database logging
            try:
                await self._log_task_start(message)
            except Exception as e:
                self.logger.error(f"failed to log task start: {e}")

        return message

    async def post_execute(
        self, message: TaskiqMessage, result: TaskiqResult[Any]
    ) -> None:
        """Consolidated post-execution handling."""

        # Let error middleware handle success recording
        await self.error_middleware.post_execute(message, result)

        if not result.is_err and self._should_log_task(message.task_name):
            # Create comprehensive context with results
            context = self._create_task_context(message, result)

            # Calculate execution metrics
            start_time = message.labels.get("_start_time")
            duration = time.perf_counter() - start_time if start_time else None

            context.update(
                {
                    "event": "task_completed",
                    "execution_status": "success",
                    "execution_duration_seconds": round(duration, 4)
                    if duration
                    else None,
                    "task_result": DataSanitizer.sanitize_data(result.return_value)
                    if result.return_value
                    else None,
                }
            )

            # Log successful completion
            self.logger.bind(**context).info(
                f"task '{message.task_name}' execution completed successfully"
            )

            # Update database
            try:
                await self._log_task_completion(message, result)
            except Exception as e:
                self.logger.error(f"failed to log task completion: {e}")

    async def on_error(
        self, message: TaskiqMessage, result: TaskiqResult[Any], exception: Exception
    ) -> None:
        """Consolidated error handling."""

        # Let error middleware handle comprehensive error processing
        await self.error_middleware.on_error(message, result, exception)

        if self._should_log_task(message.task_name):
            # Database error logging
            try:
                await self._log_task_error(message, result, exception)
            except Exception as e:
                self.logger.error(f"failed to log task error: {e}")

    def _create_task_context(
        self, message: TaskiqMessage, result: TaskiqResult = None
    ) -> dict[str, Any]:
        """Create consolidated task context with proper scope normalization."""

        trace_id = self._get_trace_id(message)
        request_id = self._get_request_id(message)

        # Sanitize and normalize task arguments
        sanitized_args = self._sanitize_task_args(message.args) if message.args else []
        sanitized_kwargs = (
            DataSanitizer.sanitize_data(message.kwargs) if message.kwargs else {}
        )
        sanitized_labels = (
            self._sanitize_labels(message.labels) if message.labels else {}
        )

        context = {
            "trace_id": str(trace_id),
            "request_id": str(request_id),
            "task_id": message.task_id,
            "task_name": message.task_name,
            "task_labels": sanitized_labels,
            "task_args": sanitized_args,
            "task_kwargs": sanitized_kwargs,
            "execution_environment": "taskiq_worker",
            "timestamp": datetime.now(di["timezone"]).isoformat(),
            "worker_id": self._get_worker_id(),
            "broker_type": self.config.broker_type.value,
            "queue": message.labels.get("queue", self.config.queue)
            if message.labels
            else self.config.queue,
            "priority": message.labels.get("priority", "normal")
            if message.labels
            else "normal",
            "retry_count": message.labels.get("retry_count", 0)
            if message.labels
            else 0,
            "max_retries": message.labels.get(
                "max_retries", self.config.default_retry_count
            )
            if message.labels
            else self.config.default_retry_count,
            "task_timeout": self.config.task_timeout,
            "memory_usage_mb": self._get_memory_usage(),
        }

        if result:
            context.update(
                {
                    "task_status": "success" if not result.is_err else "failed",
                    "task_result": str(result.return_value)
                    if not result.is_err
                    else None,
                    "task_error": str(result.error) if result.is_err else None,
                }
            )

        return context

    def _sanitize_task_args(self, args: tuple) -> list[Any]:
        """Sanitize task arguments with comprehensive scope normalization."""
        if not args:
            return []

        sanitized_args = DataSanitizer.sanitize_data(list(args))

        # Apply scope normalization to any scope-related fields
        if isinstance(sanitized_args, list):
            for _i, arg in enumerate(sanitized_args):
                if isinstance(arg, dict):
                    for key, value in arg.items():
                        if "scope" in key.lower():
                            arg[key] = ScopeNormalizer.serialize_scopes_for_json(value)

        return sanitized_args

    def _sanitize_labels(self, labels: dict) -> dict:
        """Sanitize task labels, removing non-serializable objects."""
        if not labels:
            return {}

        sanitized = {}
        for key, value in labels.items():
            # Skip internal middleware keys and non-serializable objects
            if key.startswith(("_logging_", "_otel_", "_start_", "_end_")):
                continue

            # Skip span objects and other complex objects
            if hasattr(value, "__class__") and "span" in str(type(value)).lower():
                continue

            try:
                import json

                json.dumps(value)  # Test serializability
                sanitized[key] = value
            except (TypeError, ValueError):
                sanitized[key] = str(value)[:200]

        return DataSanitizer.sanitize_data(sanitized)

    async def _log_task_start(self, message: TaskiqMessage) -> None:
        """Log task start to database."""
        await Database.connect_db()

        task_data = {
            "task_id": message.task_id,
            "task_name": message.task_name,
            "trace_id": self._get_trace_id(message),
            "request_id": self._get_request_id(message),
            "status": "running",
            "priority": message.labels.get("priority", "normal")
            if message.labels
            else "normal",
            "queue": message.labels.get("queue", self.config.queue)
            if message.labels
            else self.config.queue,
            "broker_type": self.config.broker_type.value,
            "submitted_at": datetime.now(di["timezone"]),
            "started_at": message.labels.get("_start_timestamp")
            if message.labels
            else datetime.now(di["timezone"]),
            "task_args": DataSanitizer.sanitize_data(
                self._sanitize_task_args(message.args)
            )
            if message.args
            else None,
            "task_kwargs": DataSanitizer.sanitize_data(message.kwargs)
            if message.kwargs
            else None,
            "task_labels": self._sanitize_labels(message.labels),
            "retry_count": message.labels.get("retry_count", 0)
            if message.labels
            else 0,
            "max_retries": message.labels.get(
                "max_retries", self.config.default_retry_count
            )
            if message.labels
            else self.config.default_retry_count,
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

        start_time = message.labels.get("_start_time") if message.labels else None
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

        if result.is_err and result.error:
            update_data.update(
                {
                    "task_error": str(result.error)[:1000],
                    "error_type": type(result.error).__name__,
                    "error_message": str(result.error)[:500],
                    "error_category": self._categorize_error(result.error),
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

        start_time = message.labels.get("_start_time") if message.labels else None
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

    def _should_log_task(self, task_name: str) -> bool:
        """Determine if task should be logged."""
        return (
            getattr(self.task_logging_config, "enabled", True)
            and task_name not in self.excluded_tasks
        )

    def _get_trace_id(self, message: TaskiqMessage) -> str:
        if message.labels and message.labels.get("trace_id", "unknown") != "unknown":
            return str(message.labels["trace_id"])
        if message.kwargs and message.kwargs.get("trace_id", "unknown") != "unknown":
            return str(message.kwargs["trace_id"])
        return "unknown"

    def _get_request_id(self, message: TaskiqMessage) -> str:
        if message.labels and message.labels.get("request_id", "unknown") != "unknown":
            return str(message.labels["request_id"])
        if message.kwargs and message.kwargs.get("request_id", "unknown") != "unknown":
            return str(message.kwargs["request_id"])
        return "unknown"

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
