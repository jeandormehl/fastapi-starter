from datetime import datetime
from typing import Any
from uuid import uuid4

from kink import di
from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult

from app.core.logging import get_logger


class LoggingMiddleware(TaskiqMiddleware):
    """Middleware for comprehensive task logging."""

    def __init__(self):
        super().__init__()

    async def pre_send(self, message: TaskiqMessage) -> TaskiqMessage:
        """Log task submission."""

        # Ensure trace context exists
        if "trace_id" not in message.kwargs:
            message.kwargs["trace_id"] = str(uuid4())
        if "request_id" not in message.kwargs:
            message.kwargs["request_id"] = (
                f"task-{message.task_name}-{datetime.now(di['timezone']).timestamp()}"
            )

        send_context = {
            "task_id": message.task_id,
            "task_name": message.task_name,
            "task_args": str(message.args) if message.args else None,
            "task_kwargs": message.kwargs,
            "trace_id": message.kwargs.get("trace_id"),
            "request_id": message.kwargs.get("request_id"),
            "submitted_at": datetime.now(di["timezone"]).isoformat(),
        }

        logger = get_logger(self.__class__.__module__)
        logger.bind(**send_context).info(
            f"task '{message.task_name}' submitted to broker"
        )

        return message

    async def post_send(self, message: TaskiqMessage) -> None:
        """Log successful task submission."""

        post_send_context = {
            "task_id": message.task_id,
            "task_name": message.task_name,
            "trace_id": message.kwargs.get("trace_id"),
            "request_id": message.kwargs.get("request_id"),
        }

        logger = get_logger(self.__class__.__module__)
        logger.bind(**post_send_context).info(
            f"task '{message.task_name}' successfully sent to broker"
        )

    async def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        """Log task execution start."""

        execution_context = {
            "task_id": message.task_id,
            "task_name": message.task_name,
            "task_args": str(message.args) if message.args else None,
            "task_kwargs": message.kwargs,
            "execution_start": datetime.now(di["timezone"]).isoformat(),
            "trace_id": message.kwargs.get("trace_id"),
            "request_id": message.kwargs.get("request_id"),
        }

        logger = get_logger(self.__class__.__module__)
        logger.bind(**execution_context).info(
            f"task '{message.task_name}' execution started"
        )

        # Store start time for duration calculation
        message.labels["execution_start_time"] = datetime.now(di["timezone"])

        return message

    async def post_execute(
        self, message: TaskiqMessage, result: TaskiqResult[Any]
    ) -> None:
        """Log task execution completion."""

        end_time = datetime.now(di["timezone"])
        start_time = message.labels.get("execution_start_time", end_time)
        duration = (end_time - start_time).total_seconds()

        execution_context = {
            "task_id": message.task_id,
            "task_name": message.task_name,
            "execution_end": end_time.isoformat(),
            "execution_duration_seconds": duration,
            "execution_status": "completed" if not result.is_err else "failed",
            "trace_id": message.kwargs.get("trace_id"),
            "request_id": message.kwargs.get("request_id"),
        }

        logger = get_logger(self.__class__.__module__)
        if result.is_err:
            logger.bind(**execution_context).error(
                f"task '{message.task_name}' execution failed after {duration:.2f}s"
            )
        else:
            logger.bind(**execution_context).info(
                f"task '{message.task_name}' execution completed "
                f"successfully in {duration:.2f}s"
            )

    async def post_save(
        self,
        message: TaskiqMessage,
        result: TaskiqResult[Any],  # noqa: ARG002
    ) -> None:
        """Log result storage."""
        save_context = {
            "task_id": message.task_id,
            "task_name": message.task_name,
            "result_saved": True,
            "trace_id": message.kwargs.get("trace_id"),
            "request_id": message.kwargs.get("request_id"),
        }

        logger = get_logger(self.__class__.__module__)
        logger.bind(**save_context).info(
            f"task '{message.task_name}' result saved to backend"
        )
