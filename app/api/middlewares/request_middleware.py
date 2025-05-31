import time
import traceback
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.errors.exception_handlers import EXCEPTION_HANDLERS
from app.core.logging import get_logger


class RequestMiddleware(BaseHTTPMiddleware):
    """Centralized exception handling middleware with request tracing."""

    def __init__(self, app: ASGIApp):
        super().__init__(app)

        self._logger = get_logger(__name__)

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request with comprehensive exception handling."""

        trace_id = self._get_trace_id(request)
        request_id = str(uuid.uuid4())
        start_time = time.time()

        # Store trace information in request state
        request.state.trace_id = trace_id
        request.state.request_id = request_id
        request.state.start_time = start_time

        # Enhanced request logging with more context
        request_context = {
            "trace_id": trace_id,
            "request_id": request_id,
            "client_ip": request.client.host if request.client else "unknown",
            "method": request.method,
            "url": str(request.url),
            "path": request.url.path,
            "query_params": str(request.query_params) if request.query_params else None,
            "user_agent": request.headers.get("user-agent"),
            "content_type": request.headers.get("content-type"),
            "content_length": request.headers.get("content-length"),
        }

        self._logger.bind(**request_context).info("request started")

        try:
            response = await call_next(request)

            # Log successful response with detailed metrics
            duration = time.time() - start_time
            response_context = {
                "trace_id": trace_id,
                "request_id": request_id,
                "status_code": response.status_code,
                "duration_ms": round(duration * 1000, 2),
                "response_size": response.headers.get("content-length"),
                "cache_status": response.headers.get("cache-control"),
            }

            self._logger.bind(**response_context).info("request completed successfully")

            # Add enhanced response headers
            response.headers["X-Trace-ID"] = trace_id
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time"] = f"{duration:.3f}s"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

            return response

        except Exception as exc:
            # Enhanced exception handling with detailed logging
            duration = time.time() - start_time

            # Find appropriate handler
            handler = None
            for exc_type, exc_handler in EXCEPTION_HANDLERS.items():
                if isinstance(exc, exc_type):
                    handler = exc_handler
                    break

            # Set trace variables on exception if it's an AppException
            if hasattr(exc, "request_id") and not exc.request_id:
                exc.request_id = request_id
            if hasattr(exc, "trace_id") and not exc.trace_id:
                exc.trace_id = trace_id

            if handler:
                response = await handler(request, exc)
            else:
                # Fallback to generic handler
                response = await EXCEPTION_HANDLERS[Exception](request, exc)

            # Enhanced error logging with full context
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
            }

            # Log stack trace for debugging
            if hasattr(exc, "__traceback__") and exc.__traceback__:
                error_context["traceback"] = traceback.format_exc()

            self._logger.bind(**error_context).error("request failed with exception")

            # Add trace headers to error response
            response.headers["X-Trace-ID"] = trace_id
            response.headers["X-Request-ID"] = request_id

            return response

    # noinspection PyMethodMayBeStatic
    def _get_trace_id(self, request: Request) -> str:
        """Get trace_id from header or generate new UUID."""

        # Check multiple possible header variations
        header_keys = ["x-trace-id", "trace-id", "x-correlation-id", "correlation-id"]

        for header_key in header_keys:
            for key, value in request.headers.items():
                if key.lower() == header_key:
                    try:
                        # Validate and return UUID
                        validated_uuid = uuid.UUID(value)
                        return str(validated_uuid)
                    except ValueError:
                        # Invalid UUID format, continue searching
                        continue

        # Generate new UUID if none found
        return str(uuid.uuid4())
