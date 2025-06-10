import contextlib
import time
import traceback
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.common.errors.error_response import (
    ErrorResponseBuilder,
    ErrorSeverity,
    StandardErrorResponse,
    create_error_response_json,
)
from app.common.errors.errors import ApplicationError, ErrorCode
from app.common.logging import get_logger
from app.common.utils import TraceContextExtractor


# noinspection PyBroadException
class ErrorMiddleware(BaseHTTPMiddleware):
    """
    Error handling middleware that provides standardized error responses
    using StandardErrorResponse, comprehensive error logging, and
    trace context management across all requests.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

        self._logger = get_logger(__name__)

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Process request with comprehensive exception handling."""

        # Set start time if not already set
        if not hasattr(request.state, "start_time"):
            request.state.start_time = time.time()

        try:
            return await call_next(request)

        except Exception as exc:
            return await self._handle_exception(request, exc)

    async def _handle_exception(self, request: Request, exc: Exception) -> Response:
        """Handle exception with standardized responses and comprehensive logging."""

        # Calculate request duration safely
        start_time = getattr(request.state, "start_time", time.time())
        duration = time.time() - start_time

        # Extract tracing context
        trace_id = TraceContextExtractor.get_trace_id(request)
        request_id = TraceContextExtractor.get_request_id(request)

        # Set trace variables on exception if supported
        self._set_exception_context(exc, request_id, trace_id)

        # Create standardized error response based on exception type
        error_response = self._create_standardized_error_response(
            exc, trace_id, request_id
        )

        # Determine HTTP status code
        status_code = self._determine_status_code(exc)

        # Create JSON response
        response_data = create_error_response_json(error_response, status_code)
        response = JSONResponse(**response_data)

        # Create comprehensive error context for logging
        error_context = self._create_error_context(
            request, exc, response, duration, trace_id, request_id
        )

        # Log error with appropriate severity
        severity = self._determine_log_severity(exc)
        log_method = getattr(self._logger.bind(**error_context), severity)
        log_method("request failed with exception")

        return response

    def _create_standardized_error_response(
        self, exc: Exception, trace_id: str, request_id: str
    ) -> StandardErrorResponse:
        """Create standardized error response based on exception type."""

        if isinstance(exc, ApplicationError):
            return self._handle_application_error(exc, trace_id, request_id)

        if isinstance(exc, HTTPException):
            return self._handle_http_exception(exc, trace_id, request_id)

        if isinstance(exc, RequestValidationError | ValidationError):
            return self._handle_validation_error(exc, trace_id, request_id)

        return self._handle_general_exception(exc, trace_id, request_id)

    def _handle_application_error(
        self, exc: ApplicationError, trace_id: str, request_id: str
    ) -> StandardErrorResponse:
        """Handle custom application errors."""

        error_code_mapping = {
            ErrorCode.VALIDATION_ERROR: "validation_error",
            ErrorCode.AUTHENTICATION_ERROR: "authentication_error",
            ErrorCode.AUTHORIZATION_ERROR: "authorization_error",
            ErrorCode.RESOURCE_NOT_FOUND: "not_found",
            ErrorCode.RATE_LIMIT_EXCEEDED: "rate_limit_exceeded",
            ErrorCode.INTERNAL_SERVER_ERROR: "internal_server_error",
        }

        severity_mapping = {
            ErrorCode.VALIDATION_ERROR: ErrorSeverity.LOW,
            ErrorCode.AUTHENTICATION_ERROR: ErrorSeverity.MEDIUM,
            ErrorCode.AUTHORIZATION_ERROR: ErrorSeverity.MEDIUM,
            ErrorCode.RESOURCE_NOT_FOUND: ErrorSeverity.LOW,
            ErrorCode.RATE_LIMIT_EXCEEDED: ErrorSeverity.MEDIUM,
            ErrorCode.INTERNAL_SERVER_ERROR: ErrorSeverity.CRITICAL,
        }

        return StandardErrorResponse.create(
            error=error_code_mapping.get(exc.error_code, "application_error"),
            message=exc.message,
            code=exc.error_code.value,
            details=exc.details or {},
            trace_id=trace_id,
            request_id=request_id,
            severity=severity_mapping.get(exc.error_code, ErrorSeverity.MEDIUM),
        )

    def _handle_http_exception(
        self, exc: HTTPException, trace_id: str, request_id: str
    ) -> StandardErrorResponse:
        """Handle FastAPI HTTP exceptions."""

        if exc.status_code == 400:
            return ErrorResponseBuilder.validation_error(
                message=str(exc.detail),
                trace_id=trace_id,
                request_id=request_id,
            )
        if exc.status_code == 401:
            return ErrorResponseBuilder.authentication_error(
                message=str(exc.detail),
                trace_id=trace_id,
                request_id=request_id,
            )
        if exc.status_code == 403:
            return ErrorResponseBuilder.authorization_error(
                message=str(exc.detail),
                trace_id=trace_id,
                request_id=request_id,
            )
        if exc.status_code == 404:
            return ErrorResponseBuilder.not_found_error(
                resource="resource",
                trace_id=trace_id,
                request_id=request_id,
            )
        if exc.status_code == 429:
            return ErrorResponseBuilder.rate_limit_error(
                message=str(exc.detail),
                trace_id=trace_id,
                request_id=request_id,
            )
        return ErrorResponseBuilder.internal_server_error(
            message=str(exc.detail),
            details={
                "status_code": exc.status_code,
                "exception_type": type(exc).__name__,
            },
            trace_id=trace_id,
            request_id=request_id,
        )

    def _handle_validation_error(
        self, exc: Exception, trace_id: str, request_id: str
    ) -> StandardErrorResponse:
        """Handle validation errors from Pydantic or FastAPI."""

        def _build_validation_errors(
            e: ValidationError | RequestValidationError,
        ) -> dict[str, Any]:
            _errors = []
            for error in e.errors():
                field_path = " -> ".join(str(x) for x in error["loc"])
                last_path = error["loc"][-1]
                _input = (
                    getattr(error["input"], last_path, None)
                    if isinstance(e, ValidationError)
                    else getattr(error, "input", None)
                )
                _errors.append(
                    {
                        "model": e.title if isinstance(e, ValidationError) else None,
                        "field": field_path or "root",
                        "message": error["msg"].lower(),
                        "type": error["type"],
                        "input_value": _input[:100] if _input else None,
                    }
                )
            return _errors

        if isinstance(exc, RequestValidationError | ValidationError):
            validation_errors = _build_validation_errors(exc)

            return ErrorResponseBuilder.validation_error(
                message=f"validation failed for {len(validation_errors)} field(s)",
                details={
                    "validation_errors": validation_errors,
                    "total_errors": len(validation_errors),
                },
                trace_id=trace_id,
                request_id=request_id,
            )
        return ErrorResponseBuilder.validation_error(
            message="validation error occurred",
            details={
                "exception_type": type(exc).__name__,
                "exception_message": str(exc)[:500],
            },
            trace_id=trace_id,
            request_id=request_id,
        )

    def _handle_general_exception(
        self, exc: Exception, trace_id: str, request_id: str
    ) -> StandardErrorResponse:
        """Handle general Python exceptions."""

        return ErrorResponseBuilder.internal_server_error(
            message="an unexpected error occurred",
            details={
                "exception_type": type(exc).__name__,
                "exception_message": str(exc)[:1000],
                "exception_module": getattr(exc.__class__, "__module__", "unknown"),
            },
            trace_id=trace_id,
            request_id=request_id,
        )

    def _determine_status_code(self, exc: Exception) -> int:
        """Determine appropriate HTTP status code for exception."""

        if isinstance(exc, ApplicationError | HTTPException):
            return exc.status_code

        if isinstance(exc, RequestValidationError | ValidationError):
            return status.HTTP_422_UNPROCESSABLE_ENTITY

        return status.HTTP_500_INTERNAL_SERVER_ERROR

    def _set_exception_context(
        self, exc: Exception, request_id: str, trace_id: str
    ) -> None:
        """Safely set trace context on exception if supported."""

        try:
            if hasattr(exc, "request_id") and not getattr(exc, "request_id", None):
                exc.request_id = request_id
            if hasattr(exc, "trace_id") and not getattr(exc, "trace_id", None):
                exc.trace_id = trace_id

        except Exception:
            contextlib.suppress(Exception)

    def _determine_log_severity(self, exc: Exception) -> str:
        """Determine appropriate log severity based on exception type."""

        severity = "error"

        if isinstance(exc, ApplicationError):
            if exc.error_code in {
                ErrorCode.VALIDATION_ERROR,
                ErrorCode.RESOURCE_NOT_FOUND,
            }:
                severity = "warning"
            else:
                severity = "error"

        if isinstance(exc, HTTPException):
            severity = "warning" if exc.status_code < 500 else "error"

        if isinstance(exc, RequestValidationError | ValidationError):
            severity = "warning"

        # Network/connection errors are critical
        error_msg = str(exc).lower()
        if any(
            keyword in error_msg for keyword in ["connection", "timeout", "network"]
        ):
            severity = "critical"

        return severity

    def _create_error_context(
        self,
        request: Request,
        exc: Exception,
        response: Response,
        duration: float,
        trace_id: str,
        request_id: str,
    ) -> dict[str, Any]:
        """Create comprehensive error context for logging."""

        from app.common.utils import ClientIPExtractor, DataSanitizer

        error_context = {
            "trace_id": trace_id,
            "request_id": request_id,
            "status_code": getattr(response, "status_code", 500),
            "duration_ms": round(duration * 1000, 2),
            "exception_type": type(exc).__name__,
            "exception_message": str(exc)[:1000],
            "exception_module": getattr(exc.__class__, "__module__", "unknown"),
            "request_path": self._safe_get_path(request),
            "request_method": getattr(request, "method", "UNKNOWN"),
            "client_ip": ClientIPExtractor.extract_client_ip(request),
            "event": "request_failed",
            "traceback": self._get_limited_traceback(exc),
        }

        # Add sanitized request headers
        if hasattr(request, "headers"):
            try:
                error_context["request_headers"] = DataSanitizer.sanitize_headers(
                    dict(request.headers)
                )

            except Exception:
                error_context["request_headers"] = "error_reading_headers"

        return error_context

    def _safe_get_path(self, request: Request) -> str:
        """Safely extract request path."""

        try:
            if hasattr(request, "url") and hasattr(request.url, "path"):
                return str(request.url.path)

        except Exception:
            contextlib.suppress(Exception)

        return "unknown_path"

    def _get_limited_traceback(self, exc: Exception) -> str:
        """Get limited traceback to prevent memory issues."""

        try:
            if hasattr(exc, "__traceback__") and exc.__traceback__:
                tb_lines = traceback.format_exc().split("\n")
                limited_tb = "\n".join(tb_lines[-20:])

                if len(limited_tb) > 2000:
                    limited_tb = limited_tb[:2000] + "... (truncated)"

                return limited_tb

        except Exception:
            contextlib.suppress(Exception)

        return f"error getting traceback for {type(exc).__name__}"
