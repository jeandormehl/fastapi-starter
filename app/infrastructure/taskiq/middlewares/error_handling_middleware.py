import traceback
from datetime import datetime
from typing import Any

from kink import di
from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult

from app.core.errors.exceptions import AppException, ErrorCode, ErrorDetail
from app.core.logging import get_logger


class ErrorHandlingMiddleware(TaskiqMiddleware):
    """Middleware for comprehensive error handling and monitoring."""

    def __init__(
        self,
        capture_traceback: bool = True,
        sanitize_sensitive_data: bool = True,
        enable_error_metrics: bool = True,
    ):
        super().__init__()

        self.capture_traceback = capture_traceback
        self.sanitize_sensitive_data = sanitize_sensitive_data
        self.enable_error_metrics = enable_error_metrics

        # Error metrics
        self.error_counts: dict[str, int] = {}
        self.last_errors: dict[str, dict[str, Any]] = {}

    def _sanitize_data(self, data: Any) -> Any:
        """Sanitize sensitive data for logging."""

        if not self.sanitize_sensitive_data:
            return data

        if isinstance(data, dict):
            sanitized = {}
            for key, value in data.items():
                if any(
                    sensitive in key.lower()
                    for sensitive in ["password", "secret", "token", "key", "auth"]
                ):
                    sanitized[key] = "[REDACTED]"
                else:
                    sanitized[key] = self._sanitize_data(value)
            return sanitized

        if isinstance(data, list | tuple):
            return [self._sanitize_data(item) for item in data]

        return data

    def _create_error_context(
        self,
        message: TaskiqMessage,
        exception: Exception,
        result: TaskiqResult | None = None,
    ) -> dict[str, Any]:
        """Create comprehensive error context."""

        context = {
            "task_id": message.task_id,
            "task_name": message.task_name,
            "exception_type": type(exception).__name__,
            "exception_message": str(exception),
            "exception_module": getattr(exception.__class__, "__module__", "unknown"),
            "timestamp": datetime.now(di["timezone"]).isoformat(),
            "trace_id": message.kwargs.get("trace_id"),
            "request_id": message.kwargs.get("request_id"),
        }

        # Add task execution context
        if message.args:
            context["task_args"] = self._sanitize_data(list(message.args))

        if message.kwargs:
            context["task_kwargs"] = self._sanitize_data(message.kwargs)

        # Add result information if available
        if result:
            context.update(
                {
                    "task_result_is_error": result.is_err,
                    "task_result_log": result.log,
                }
            )

            if result.return_value:
                context["task_result_value"] = str(result.return_value)[:1000]

        # Add traceback if enabled
        if self.capture_traceback:
            context["traceback"] = traceback.format_exc()

        # Add app-specific error details
        if isinstance(exception, AppException):
            context.update(
                {
                    "app_error_code": exception.error_code.value,
                    "app_error_details": exception.details,
                    "app_error_status_code": exception.status_code,
                }
            )

        return context

    def _update_error_metrics(self, message: TaskiqMessage, exception: Exception):
        """Update error metrics for monitoring."""

        if not self.enable_error_metrics:
            return

        error_key = f"{message.task_name}:{type(exception).__name__}"

        # Update error counts
        self.error_counts[error_key] = self.error_counts.get(error_key, 0) + 1

        # Store last error details
        self.last_errors[error_key] = {
            "task_id": message.task_id,
            "timestamp": datetime.now(di["timezone"]).isoformat(),
            "exception_message": str(exception),
            "count": self.error_counts[error_key],
        }

    def _create_error_detail(
        self, message: TaskiqMessage, exception: Exception
    ) -> ErrorDetail:
        """Create standardized error detail."""

        if isinstance(exception, AppException):
            error_code = exception.error_code.value
            details = exception.details.copy()
        else:
            error_code = ErrorCode.INTERNAL_SERVER_ERROR.value
            details = {}

        details.update(
            {
                "task_name": message.task_name,
                "task_id": message.task_id,
                "exception_type": type(exception).__name__,
                "execution_context": "taskiq_worker",
            }
        )

        return ErrorDetail(
            code=error_code,
            message=f"Task '{message.task_name}' failed: {exception!s}",
            details=details,
            trace_id=message.kwargs.get("trace_id"),
            request_id=message.kwargs.get("request_id"),
            timestamp=datetime.now(di["timezone"]).isoformat(),
        )

    async def on_error(
        self, message: TaskiqMessage, result: TaskiqResult[Any], exception: Exception
    ) -> None:
        """Handle task execution errors with comprehensive logging and monitoring."""

        # Create error context
        error_context = self._create_error_context(message, exception, result)

        # Update metrics
        self._update_error_metrics(message, exception)

        # Determine log level based on exception type
        if isinstance(exception, AppException):
            if exception.error_code in {
                ErrorCode.VALIDATION_ERROR,
                ErrorCode.AUTHENTICATION_ERROR,
                ErrorCode.AUTHORIZATION_ERROR,
                ErrorCode.RESOURCE_NOT_FOUND,
            }:
                log_level = "warning"
            else:
                log_level = "error"
        else:
            log_level = "error"

        # Log the error
        logger = get_logger(__name__)
        log_method = getattr(logger.bind(**error_context), log_level)
        log_method(f"task '{message.task_name}' execution failed: {exception}")

        # Create standardized error detail for the result
        error_detail = self._create_error_detail(message, exception)

        # Update result with error detail
        result.return_value = error_detail.model_dump()
        result.log = error_detail.message

    def get_error_metrics(self) -> dict[str, Any]:
        """Get current error metrics for monitoring."""

        return {
            "error_counts": self.error_counts.copy(),
            "last_errors": self.last_errors.copy(),
            "total_unique_errors": len(self.error_counts),
            "total_error_count": sum(self.error_counts.values()),
        }
