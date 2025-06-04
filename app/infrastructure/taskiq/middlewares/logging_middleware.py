import time
from datetime import datetime
from typing import Any

from kink import di
from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult

from app.core.logging import get_logger
from app.core.utils import sanitize_for_logging


class LoggingMiddleware(TaskiqMiddleware):
    """Comprehensive logging middleware for Taskiq tasks."""

    def __init__(self, log_task_args: bool = True, log_task_results: bool = False):
        super().__init__()

        self.log_task_args = log_task_args
        self.log_task_results = log_task_results

    def _create_base_context(self, message: TaskiqMessage) -> dict[str, Any]:
        """Create base logging context from message."""

        context = {
            "task_id": message.task_id,
            "task_name": message.task_name,
            "task_labels": message.labels,
            "execution_context": "taskiq_middleware",
            "trace_id": message.kwargs.get("trace_id"),
            "request_id": message.kwargs.get("request_id"),
            "timestamp": datetime.now(di["timezone"]).isoformat(),
        }

        if self.log_task_args and message.args:
            context["task_args"] = str(message.args)[:500]

        if self.log_task_args and message.kwargs:
            # Sanitize sensitive data
            sanitized_kwargs = sanitize_for_logging(message.kwargs)
            context["task_kwargs"] = sanitized_kwargs

        return context

    async def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        """Log task execution start."""

        context = self._create_base_context(message)
        context.update(
            {
                "event": "task_started",
                "execution_status": "starting",
            }
        )

        logger = get_logger(__name__)
        logger.bind(**context).info(f"starting task '{message.task_name}' execution")

        # Store start time for duration calculation
        message.labels["_middleware_start_time"] = time.time()

        return message

    async def post_execute(
        self, message: TaskiqMessage, result: TaskiqResult[Any]
    ) -> None:
        """Log task execution completion."""

        logger = get_logger(__name__)

        start_time = message.labels.get("_middleware_start_time")
        duration = time.time() - start_time if start_time else None

        context = self._create_base_context(message)
        context.update(
            {
                "event": "task_completed",
                "execution_status": "failed" if result.is_err else "success",
                "is_error": result.is_err,
                "execution_duration_seconds": round(duration, 3) if duration else None,
            }
        )

        if result.is_err:
            context.update(
                {
                    "error_log": result.log,
                    "error_return_value": str(result.return_value)[:1000]
                    if result.return_value
                    else None,
                }
            )

            logger.bind(**context).error(
                f"task '{message.task_name}' execution failed: {result.log}"
            )
        else:
            if self.log_task_results and result.return_value is not None:
                context["task_result"] = str(result.return_value)[:500]

            logger.bind(**context).info(
                f"task '{message.task_name}' execution completed successfully"
            )

    async def on_error(
        self, message: TaskiqMessage, _result: TaskiqResult[Any], exception: Exception
    ) -> None:
        """Log task execution errors."""
        start_time = message.labels.get("_middleware_start_time")
        duration = time.time() - start_time if start_time else None

        context = self._create_base_context(message)
        context.update(
            {
                "event": "task_error",
                "execution_status": "error",
                "exception_type": type(exception).__name__,
                "exception_message": str(exception),
                "execution_duration_seconds": round(duration, 3) if duration else None,
            }
        )

        logger = get_logger(__name__)
        logger.bind(**context).error(
            f"task '{message.task_name}' raised exception: {exception}",
            exc_info=exception,
        )
