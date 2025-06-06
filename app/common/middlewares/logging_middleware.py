import time
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.logging import get_logger


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for comprehensive request/response logging with performance metrics.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

        self._logger = get_logger(__name__)

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Process request with comprehensive logging."""

        start_time = time.time()

        # Store start time in request state
        request.state.start_time = start_time

        # Create request context for logging
        request_context = self._create_request_context(request)

        # Log request start
        self._logger.bind(**request_context).info("request started")

        # Process request
        response = await call_next(request)

        # Calculate duration and log response
        duration = time.time() - start_time
        response_context = self._create_response_context(request, response, duration)

        self._logger.bind(**response_context).info("request completed successfully")

        # Add performance header
        response.headers["X-Response-Time"] = f"{duration:.3f}s"

        return response

    def _create_request_context(self, request: Request) -> dict[str, Any]:
        """Create comprehensive request context for logging."""

        return {
            "trace_id": getattr(request.state, "trace_id", "unknown"),
            "request_id": getattr(request.state, "request_id", "unknown"),
            "client_ip": request.client.host if request.client else "unknown",
            "method": request.method,
            "url": str(request.url),
            "path": request.url.path,
            "query_params": str(request.query_params) if request.query_params else None,
            "user_agent": request.headers.get("user-agent"),
            "content_type": request.headers.get("content-type"),
            "content_length": request.headers.get("content-length"),
            "event": "request_started",
        }

    def _create_response_context(
        self, request: Request, response: Response, duration: float
    ) -> dict[str, Any]:
        """Create comprehensive response context for logging."""

        return {
            "trace_id": getattr(request.state, "trace_id", "unknown"),
            "request_id": getattr(request.state, "request_id", "unknown"),
            "status_code": response.status_code,
            "duration_ms": round(duration * 1000, 2),
            "response_size": response.headers.get("content-length"),
            "cache_status": response.headers.get("cache-control"),
            "event": "request_completed",
        }
