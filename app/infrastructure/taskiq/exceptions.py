from typing import Any

from fastapi import status

from app.core.errors.exceptions import AppException, ErrorCode


class TaskException(AppException):
    """Exception for Taskiq task-related errors."""

    def __init__(
        self,
        task_name: str,
        message: str,
        task_id: str | None = None,
        task_args: tuple | None = None,
        task_kwargs: dict[str, Any] | None = None,
        error_code: ErrorCode = ErrorCode.INTERNAL_SERVER_ERROR,
        details: dict[str, Any] | None = None,
        cause: Exception | None = None,
    ):
        details = details or {}
        details.update(
            {
                "task_name": task_name,
                "task_id": task_id,
                "task_args": str(task_args) if task_args else None,
                "task_kwargs": task_kwargs,
                "execution_context": "task_worker",
            }
        )

        message = f"task '{task_name}' error: {message}"

        super().__init__(
            error_code=error_code,
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details,
            cause=cause,
        )
