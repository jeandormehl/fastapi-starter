import time
import traceback
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.errors.exception_handlers import EXCEPTION_HANDLERS
from app.core.logging import get_logger


class ErrorMiddleware(BaseHTTPMiddleware):
    """
    Middleware for centralized exception handling with comprehensive error logging.
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)

        self._logger = get_logger(__name__)

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request with comprehensive exception handling."""

        try:
            return await call_next(request)

        except Exception as exc:
            return await self._handle_exception(request, exc)

    async def _handle_exception(self, request: Request, exc: Exception) -> Response:
        """Handle exception with comprehensive logging and response generation."""

        # Calculate request duration
        start_time = getattr(request.state, "start_time", time.time())
        duration = time.time() - start_time

        # Extract tracing context
        trace_id = getattr(request.state, "trace_id", "unknown")
        request_id = getattr(request.state, "request_id", "unknown")

        # Set trace variables on exception if it's an AppException
        if hasattr(exc, "request_id") and not exc.request_id:
            exc.request_id = request_id

        if hasattr(exc, "trace_id") and not exc.trace_id:
            exc.trace_id = trace_id

        # Find appropriate exception handler
        handler = self._find_exception_handler(exc)

        # Generate error response
        response = await handler(request, exc)

        # Log error with comprehensive context
        error_context = self._create_error_context(
            request, exc, response, duration, trace_id, request_id
        )

        self._logger.bind(**error_context).error("request failed with exception")

        # Add trace headers to error response
        response.headers["X-Trace-ID"] = trace_id
        response.headers["X-Request-ID"] = request_id

        return response

    def _find_exception_handler(self, exc: Exception):
        """Find appropriate exception handler for the given exception."""

        # Find specific handler for exception type
        for exc_type, exc_handler in EXCEPTION_HANDLERS.items():
            if isinstance(exc, exc_type):
                return exc_handler

        # Fallback to generic Exception handler
        return EXCEPTION_HANDLERS[Exception]

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

        error_context = {
            "trace_id": trace_id,
            "request_id": request_id,
            "status_code": response.status_code,
            "duration_ms": round(duration * 1000, 2),
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "exception_module": getattr(exc.__class__, "__module__", "unknown"),
            "request_path": request.url.path,
            "request_method": request.method,
            "client_ip": request.client.host if request.client else "unknown",
            "event": "request_failed",
        }

        # Add stack trace for debugging
        if hasattr(exc, "__traceback__") and exc.__traceback__:
            error_context["traceback"] = traceback.format_exc()

        return error_context
