import traceback
from datetime import datetime
from typing import Any

from celery import Task
from celery.exceptions import Retry, WorkerLostError
from fastapi import status
from kink import di

from app.core.errors.exceptions import AppException, ErrorCode, ErrorDetail
from app.core.logging import get_logger


class TaskException(AppException):
    """Exception for Celery task-related errors."""

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
        enhanced_details = details or {}
        enhanced_details.update(
            {
                "task_name": task_name,
                "task_id": task_id,
                "task_args": str(task_args) if task_args else None,
                "task_kwargs": task_kwargs,
                "execution_context": "celery_worker",
            }
        )

        full_message = f"celery task '{task_name}' error: {message}"

        super().__init__(
            error_code=error_code,
            message=full_message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=enhanced_details,
            cause=cause,
        )


class BaseTask(Task):
    """Base task with comprehensive callbacks, logging, and error handling."""

    def __init__(self):
        super().__init__()

        self.logger = get_logger(self.__class__.__module__)

    def on_success(
        self, retval: Any, task_id: str, args: tuple, kwargs: dict[str, Any]
    ):
        """Handle successful task completion with detailed logging."""

        execution_context = {
            "task_id": task_id,
            "task_name": self.name,
            "task_args": str(args) if args else None,
            "task_kwargs": kwargs,
            "return_value": str(retval)[:500] if retval else None,  # Limit size
            "execution_status": "success",
            "timestamp": datetime.now(di["timezone"]).isoformat(),
        }

        self.logger.bind(**execution_context).info(
            f"celery task '{self.name}' completed successfully"
        )

        # Call any custom success handling
        self._handle_success(retval, task_id, args, kwargs)

    def on_failure(
        self,
        exc: Exception,
        task_id: str,
        args: tuple,
        kwargs: dict[str, Any],
        einfo: Any,
    ):
        """Handle task failure with comprehensive error logging."""

        # Determine error classification
        if isinstance(exc, Retry):
            error_code = ErrorCode.EXTERNAL_SERVICE_TIMEOUT
            log_level = "warning"
            message = "task retry scheduled"
        elif isinstance(exc, WorkerLostError):
            error_code = ErrorCode.INTERNAL_SERVER_ERROR
            log_level = "critical"
            message = "worker lost during task execution"
        elif isinstance(exc, AppException):
            error_code = exc.error_code
            log_level = "error"
            message = exc.message
        else:
            error_code = ErrorCode.INTERNAL_SERVER_ERROR
            log_level = "error"
            message = str(exc)

        # Create standardized error detail
        error_detail = ErrorDetail(
            code=str(error_code.value),
            message=f"celery task '{self.name}' failed: {message}",
            details={
                "task_id": task_id,
                "task_name": self.name,
                "task_args": str(args) if args else None,
                "task_kwargs": kwargs,
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
                "traceback": str(einfo) if einfo else traceback.format_exc(),
                "execution_context": "celery_worker",
                "failure_timestamp": datetime.now(di["timezone"]).isoformat(),
            },
            timestamp=datetime.now(di["timezone"]).isoformat(),
            trace_id=kwargs.get("trace_id"),
            request_id=kwargs.get("request_id"),
        )

        # Log with appropriate level
        log_context = error_detail.model_dump(exclude_none=True)
        bound_logger = self.logger.bind(**log_context)

        if log_level == "critical":
            bound_logger.critical("celery task critical failure")
        elif log_level == "warning":
            bound_logger.warning("celery task retry or recoverable failure")
        else:
            bound_logger.error("celery task execution failed")

        # Call any custom failure handling
        self._handle_failure(exc, task_id, args, kwargs, einfo, error_detail)

    def on_retry(
        self,
        exc: Exception,
        task_id: str,
        args: tuple,
        kwargs: dict[str, Any],
        einfo: Any,
    ):
        """Handle task retry with logging."""

        retry_context = {
            "task_id": task_id,
            "task_name": self.name,
            "task_args": str(args) if args else None,
            "task_kwargs": kwargs,
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "retry_count": self.request.retries,
            "max_retries": self.max_retries,
            "execution_context": "celery_worker",
            "retry_timestamp": datetime.now(di["timezone"]).isoformat(),
        }

        self.logger.bind(**retry_context).warning(
            f"celery task '{self.name}' retry {self.request.retries}/{self.max_retries}"
        )

        # Call any custom retry handling
        self._handle_retry(exc, task_id, args, kwargs, einfo)

    def apply_async(self, args=None, kwargs=None, **options):
        """Override apply_async to add execution context."""

        # Add trace context if not present
        kwargs = kwargs or {}
        if "trace_id" not in kwargs:
            kwargs["trace_id"] = f"celery-{datetime.now(di['timezone']).timestamp()}"
        if "request_id" not in kwargs:
            kwargs["request_id"] = (
                f"task-{self.name}-{datetime.now(di['timezone']).timestamp()}"
            )

        # Log task initiation
        initiation_context = {
            "task_name": self.name,
            "task_args": str(args) if args else None,
            "task_kwargs": kwargs,
            "trace_id": kwargs.get("trace_id"),
            "request_id": kwargs.get("request_id"),
            "initiated_at": datetime.now(di["timezone"]).isoformat(),
        }

        self.logger.bind(**initiation_context).info(
            f"celery task '{self.name}' initiated"
        )

        return super().apply_async(args=args, kwargs=kwargs, **options)

    def _handle_success(
        self, retval: Any, task_id: str, args: tuple, kwargs: dict[str, Any]
    ):
        """Override this method for custom success handling."""

    def _handle_failure(
        self,
        exc: Exception,
        task_id: str,
        args: tuple,
        kwargs: dict[str, Any],
        einfo: Any,
        error_detail: ErrorDetail,
    ):
        """Override this method for custom failure handling."""

    def _handle_retry(
        self,
        exc: Exception,
        task_id: str,
        args: tuple,
        kwargs: dict[str, Any],
        einfo: Any,
    ):
        """Override this method for custom retry handling."""

    def __call__(self, *args, **kwargs):
        """Override __call__ to add execution logging and error handling."""

        start_time = datetime.now(di["timezone"])

        execution_context = {
            "task_id": self.request.id,
            "task_name": self.name,
            "task_args": str(args) if args else None,
            "task_kwargs": kwargs,
            "execution_start": start_time.isoformat(),
            "worker_id": self.request.hostname,
            "trace_id": kwargs.get("trace_id"),
            "request_id": kwargs.get("request_id"),
        }

        self.logger.bind(**execution_context).info(
            f"celery task '{self.name}' execution started"
        )

        try:
            result = super().__call__(*args, **kwargs)

            end_time = datetime.now(di["timezone"])
            duration = (end_time - start_time).total_seconds()

            # Log successful execution
            completion_context = {
                **execution_context,
                "execution_end": end_time.isoformat(),
                "execution_duration_seconds": duration,
                "execution_status": "completed",
            }

            self.logger.bind(**completion_context).info(
                f"celery task '{self.name}' execution completed in {duration:.2f}s"
            )

            return result

        except Exception as exc:
            end_time = datetime.now(di["timezone"])
            duration = (end_time - start_time).total_seconds()

            # Create enhanced exception for task context
            if not isinstance(exc, TaskException):
                enhanced_exc = TaskException(
                    task_name=self.name,
                    message=str(exc),
                    task_id=self.request.id,
                    task_args=args,
                    task_kwargs=kwargs,
                    details={
                        "execution_duration_seconds": duration,
                        "worker_id": self.request.hostname,
                    },
                    cause=exc,
                )
            else:
                enhanced_exc = exc

            # Log execution failure
            failure_context = {
                **execution_context,
                "execution_end": end_time.isoformat(),
                "execution_duration_seconds": duration,
                "execution_status": "failed",
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            }

            self.logger.bind(**failure_context).error(
                f"celery task '{self.name}' execution failed after {duration:.2f}s"
            )

            raise enhanced_exc
