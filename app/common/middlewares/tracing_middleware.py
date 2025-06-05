import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp


class TracingMiddleware(BaseHTTPMiddleware):
    """Middleware for request tracing and correlation ID management."""

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request with tracing context setup."""

        # Generate or extract trace and request IDs
        trace_id = self._get_trace_id(request)
        request_id = str(uuid.uuid4())

        # Store trace information in request state for downstream use
        request.state.trace_id = trace_id
        request.state.request_id = request_id

        # Process request
        response = await call_next(request)

        # Add tracing headers to response
        self._add_trace_headers(response, trace_id, request_id)

        return response

    def _get_trace_id(self, request: Request) -> str:
        """Extract trace_id from headers or generate new UUID."""

        # Check multiple possible header variations following OpenTelemetry standards
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

    def _add_trace_headers(
        self, response: Response, trace_id: str, request_id: str
    ) -> None:
        """Add tracing and security headers to response."""

        # Tracing headers
        response.headers["X-Trace-ID"] = trace_id
        response.headers["X-Request-ID"] = request_id

        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
