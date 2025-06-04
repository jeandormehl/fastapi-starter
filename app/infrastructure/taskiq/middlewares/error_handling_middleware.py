from datetime import datetime
from typing import Any

from kink import di
from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult

from app.core.errors.exceptions import AppException, ErrorCode, ErrorDetail
from app.core.logging import get_logger
from app.infrastructure.taskiq.exceptions import TaskException


class ErrorHandlingMiddleware(TaskiqMiddleware):
    """Middleware for comprehensive error handling and monitoring."""

    def __init__(self):
        super().__init__()

    async def on_error(
        self, message: TaskiqMessage, result: TaskiqResult[Any], exception: Exception
    ) -> None:
        """Handle task execution errors."""

        # Determine error classification
        if isinstance(exception, AppException | TaskException):
            error_code = exception.error_code
            error_message = exception.message
        else:
            error_code = ErrorCode.INTERNAL_SERVER_ERROR
            error_message = str(exception)

        # Create standardized error detail
        error_detail = ErrorDetail(
            code=str(error_code.value),
            message=f"taskiq task '{message.task_name}' failed: {error_message}",
            details={
                "task_id": message.task_id,
                "task_name": message.task_name,
                "task_args": str(message.args) if message.args else None,
                "task_kwargs": message.kwargs,
                "exception_type": type(exception).__name__,
                "exception_message": str(exception),
                "execution_context": "taskiq_worker",
                "failure_timestamp": datetime.now(di["timezone"]).isoformat(),
            },
            timestamp=datetime.now(di["timezone"]).isoformat(),
            trace_id=message.kwargs.get("trace_id"),
            request_id=message.kwargs.get("request_id"),
        )

        # Log error with full context
        log_context = error_detail.model_dump(exclude_none=True)

        logger = get_logger(__class__.__module__)
        logger.bind(**log_context).error("task execution error")

        # Update result with enhanced error information
        result.error = error_detail.model_dump()
