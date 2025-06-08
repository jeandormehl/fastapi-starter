import contextlib
import time
import traceback
from typing import Any

from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.common.errors import (
    EXCEPTION_HANDLERS,
    ErrorResponseBuilder,
    create_error_response_json,
)
from app.common.logging import get_logger
from app.common.utils import TraceContextExtractor


# noinspection PyBroadException
class ErrorMiddleware(BaseHTTPMiddleware):
    """
    Error handling middleware that provides standardized error responses,
    comprehensive error logging, and trace context management across all requests.
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

        # Find appropriate exception handler and generate standardized response
        handler = self._find_exception_handler(exc)
        response = await handler(request, exc)

        # Create comprehensive error context for logging
        error_context = self._create_error_context(
            request, exc, response, duration, trace_id, request_id
        )

        # Log error with appropriate severity
        severity = self._determine_log_severity(exc)
        log_method = getattr(self._logger.bind(**error_context), severity)
        log_method("request failed with exception")

        # Add standard trace headers to error response
        response.headers["X-Trace-ID"] = trace_id
        response.headers["X-Request-ID"] = request_id

        return response

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

    def _find_exception_handler(self, exc: Exception) -> Any:
        """Find appropriate exception handler for the given exception."""

        for exc_type, exc_handler in EXCEPTION_HANDLERS.items():
            if isinstance(exc, exc_type):
                return exc_handler

        return EXCEPTION_HANDLERS.get(Exception, self._default_exception_handler)

    def _determine_log_severity(self, exc: Exception) -> str:
        """Determine appropriate log severity based on exception type."""

        from app.common.errors.errors import ApplicationError, ErrorCode

        if isinstance(exc, ApplicationError):
            if exc.error_code in {
                ErrorCode.VALIDATION_ERROR,
                ErrorCode.RESOURCE_NOT_FOUND,
            }:
                return "info"

            if exc.error_code in {
                ErrorCode.AUTHENTICATION_ERROR,
                ErrorCode.AUTHORIZATION_ERROR,
            }:
                return "warning"

            return "error"

        # Network/connection errors are critical
        error_msg = str(exc).lower()
        if any(
            keyword in error_msg for keyword in ["connection", "timeout", "network"]
        ):
            return "critical"

        return "error"

    async def _default_exception_handler(
        self, request: Request, exc: Exception
    ) -> JSONResponse:
        """Default exception handler with standardized response format."""

        trace_id = TraceContextExtractor.get_trace_id(request)
        request_id = TraceContextExtractor.get_request_id(request)

        error_response = ErrorResponseBuilder.internal_server_error(
            message="an unexpected error occurred",
            details={
                "exception_type": type(exc).__name__,
                "exception_message": str(exc)[:1000],
                "exception_module": getattr(exc.__class__, "__module__", "unknown"),
            },
            trace_id=trace_id,
            request_id=request_id,
        )

        response_data = create_error_response_json(
            error_response, status.HTTP_500_INTERNAL_SERVER_ERROR
        )

        return JSONResponse(**response_data)

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
