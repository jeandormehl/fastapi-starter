import traceback
from datetime import datetime
from typing import Any
from uuid import uuid4

from kink import di

from app.core.errors.exceptions import AppException, ErrorCode, ErrorDetail
from app.core.logging import get_logger
from app.infrastructure.taskiq.exceptions import TaskException


class BaseTask:
    """Base task class for Taskiq with comprehensive error handling and logging."""

    def __init__(self, task_name: str):
        self.task_name = task_name
        self.logger = get_logger(self.__class__.__module__)

    def create_execution_context(
        self, task_id: str, args: tuple, kwargs: dict[str, Any]
    ) -> dict[str, Any]:
        """Create standardized execution context for logging."""

        return {
            "task_id": task_id,
            "task_name": self.task_name,
            "task_args": str(args) if args else None,
            "task_kwargs": kwargs,
            "execution_context": "worker",
            "trace_id": kwargs.get("trace_id", str(uuid4())),
            "request_id": kwargs.get(
                "request_id",
                f"task-{self.task_name}-{datetime.now(di['timezone']).timestamp()}",
            ),
        }

    def handle_task_success(
        self, result: Any, execution_context: dict[str, Any], duration: float
    ) -> None:
        """Handle successful task completion."""

        success_context = {
            **execution_context,
            "return_value": str(result)[:500] if result else None,
            "execution_status": "success",
            "execution_duration_seconds": duration,
            "timestamp": datetime.now(di["timezone"]).isoformat(),
        }

        self.logger.bind(**success_context).info(
            f"task '{self.task_name}' completed successfully in {duration:.2f}s"
        )

    def handle_task_failure(
        self, exc: Exception, execution_context: dict[str, Any], duration: float
    ) -> TaskException:
        """Handle task failure with comprehensive error logging."""

        # Determine error classification
        if isinstance(exc, AppException):
            error_code = exc.error_code
            message = exc.message
        else:
            error_code = ErrorCode.INTERNAL_SERVER_ERROR
            message = str(exc)

        # Create enhanced exception
        exc = TaskException(
            task_name=self.task_name,
            message=message,
            task_id=execution_context.get("task_id"),
            task_args=execution_context.get("task_args"),
            task_kwargs=execution_context.get("task_kwargs"),
            error_code=error_code,
            details={
                "execution_duration_seconds": duration,
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
                "traceback": traceback.format_exc(),
            },
            cause=exc,
        )

        # Create error detail for logging
        error_detail = ErrorDetail(
            code=str(error_code.value),
            message=exc.message,
            details=exc.details,
            timestamp=datetime.now(di["timezone"]).isoformat(),
            trace_id=execution_context.get("trace_id"),
            request_id=execution_context.get("request_id"),
        )

        # Log with appropriate context
        log_context = {
            **execution_context,
            **error_detail.model_dump(exclude_none=True),
            "execution_status": "failed",
            "execution_duration_seconds": duration,
        }

        self.logger.bind(**log_context).error(
            f"task '{self.task_name}' execution failed after {duration:.2f}s"
        )

        return exc
