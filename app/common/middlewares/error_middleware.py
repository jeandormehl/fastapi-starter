import contextlib
import time
import traceback
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.errors.exception_handlers import EXCEPTION_HANDLERS
from app.core.logging import get_logger


# noinspection PyBroadException
class ErrorMiddleware(BaseHTTPMiddleware):
    """
    Middleware for centralized exception handling with comprehensive error logging.
    Enhanced with defensive programming and better error context management.
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
        """Handle exception with comprehensive logging and response generation."""

        # Calculate request duration safely
        start_time = getattr(request.state, "start_time", time.time())
        duration = time.time() - start_time

        # Extract tracing context with defaults
        trace_id = self._get_trace_id(request)
        request_id = self._get_request_id(request)

        # Set trace variables on exception if it's an AppException (defensive)
        self._set_exception_context(exc, request_id, trace_id)

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

    def _get_trace_id(self, request: Request) -> str:
        """Safely extract trace ID from request state."""

        if hasattr(request, "state") and hasattr(request.state, "trace_id"):
            trace_id = getattr(request.state, "trace_id", None)
            if trace_id:
                return str(trace_id)

        # Generate fallback trace ID
        return "unknown"

    def _get_request_id(self, request: Request) -> str:
        """Safely extract request ID from request state."""

        if hasattr(request, "state") and hasattr(request.state, "request_id"):
            request_id = getattr(request.state, "request_id", None)
            if request_id:
                return str(request_id)

        # Generate fallback request ID
        return "unknown"

    def _set_exception_context(
        self, exc: Exception, request_id: str, trace_id: str
    ) -> None:
        """Safely set trace context on exception if supported."""

        try:
            # Only set if the exception has these attributes and they're not already set
            if hasattr(exc, "request_id") and not getattr(exc, "request_id", None):
                exc.request_id = request_id

            if hasattr(exc, "trace_id") and not getattr(exc, "trace_id", None):
                exc.trace_id = trace_id

        except Exception:
            # Ignore errors in setting context to prevent masking the original exception
            contextlib.suppress(Exception)

    def _find_exception_handler(self, exc: Exception) -> Any:
        """Find appropriate exception handler for the given exception."""

        # Find specific handler for exception type
        for exc_type, exc_handler in EXCEPTION_HANDLERS.items():
            if isinstance(exc, exc_type):
                return exc_handler

        # Fallback to generic Exception handler
        return EXCEPTION_HANDLERS.get(Exception, self._default_exception_handler)

    async def _default_exception_handler(
        self, _request: Request, _exc: Exception
    ) -> Response:
        """Default exception handler for cases where no specific handler is found."""

        from starlette.responses import JSONResponse

        return JSONResponse(
            status_code=500,
            content={
                "error": "internal server error",
                "message": "an unexpected error occurred",
                "code": "internal_server_error",
            },
        )

    def _create_error_context(
        self,
        request: Request,
        exc: Exception,
        response: Response,
        duration: float,
        trace_id: str,
        request_id: str,
    ) -> dict[str, Any]:
        """Create comprehensive error context for logging with enhanced safety."""

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
            "client_ip": self._safe_get_client_ip(request),
            "event": "request_failed",
            "traceback": self._get_limited_traceback(exc),
        }

        # Add limited stack trace for debugging (prevent memory issues)

        # Add request headers safely
        if hasattr(request, "headers"):
            try:
                # Only include non-sensitive headers
                safe_headers = {
                    k: v
                    for k, v in request.headers.items()
                    if k.lower() not in {"authorization", "cookie", "x-api-key"}
                }
                error_context["request_headers"] = dict(safe_headers)
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

    def _safe_get_client_ip(self, request: Request) -> str:
        """Safely extract client IP address."""

        try:
            if hasattr(request, "client") and request.client:
                return getattr(request.client, "host", "unknown")
        except Exception:
            contextlib.suppress(Exception)

        return "unknown_ip"

    def _get_limited_traceback(self, exc: Exception) -> str:
        """Get limited traceback to prevent memory issues."""

        try:
            if hasattr(exc, "__traceback__") and exc.__traceback__:
                # Limit traceback to last 10 frames and 2000 characters
                tb_lines = traceback.format_exc().split("\n")
                limited_tb = "\n".join(tb_lines[-20:])  # Last 20 lines

                if len(limited_tb) > 2000:
                    limited_tb = limited_tb[:2000] + "... (truncated)"

                return limited_tb
        except Exception:
            contextlib.suppress(Exception)

        return f"error getting traceback for {type(exc).__name__}"
