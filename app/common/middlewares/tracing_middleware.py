import time
import uuid
from typing import Any

from fastapi import Request
from opentelemetry import context, trace
from opentelemetry.propagate import extract, inject
from opentelemetry.trace import Span, Status, StatusCode
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp

from app.common.logging import get_logger
from app.common.utils import ClientIPExtractor
from app.infrastructure.observability.metrics import get_meter
from app.infrastructure.observability.tracing import get_tracer


class TracingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for request tracing with full otel integration.
    Handles correlation ID management, span creation, and context propagation.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

        self.tracer = get_tracer("app.requests")
        self.meter = get_meter("app.requests")
        self.logger = get_logger(__name__)

        # Create metrics
        self.request_duration = self.meter.create_histogram(
            name="http_request_duration_ms",
            description="HTTP request duration in milliseconds",
            unit="ms",
        )

        self.request_counter = self.meter.create_counter(
            name="http_requests_total",
            description="Total number of HTTP requests",
        )

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Process request with comprehensive tracing context setup."""

        # Skip tracing for health/metrics endpoints
        if self._should_skip_tracing(request):
            return await call_next(request)

        # Extract or generate trace context
        trace_id = self._get_trace_id(request)
        request_id = str(uuid.uuid4())

        # Store trace information in request state
        request.state.trace_id = trace_id
        request.state.request_id = request_id

        # Extract OpenTelemetry context from headers
        carrier = dict(request.headers)
        otel_context = extract(carrier)

        # Start timing
        start_time = time.time()

        # Create span with extracted context
        with context.attach(otel_context):
            span = self.tracer.start_span(
                f"{request.method} {request.url.path}", kind=trace.SpanKind.SERVER
            )

            # Set span attributes
            self._set_span_attributes(span, request, trace_id, request_id)

            # Store span in request state for downstream middleware
            request.state.otel_span = span
            request.state.otel_context = otel_context

            try:
                # Make span current and process request
                token = context.attach(trace.set_span_in_context(span))

                try:
                    response = await call_next(request)

                    # Record successful request
                    self._record_success_metrics(request, response, start_time)
                    self._finalize_successful_span(span, request, response, start_time)

                    # Add tracing headers to response
                    self._add_trace_headers(response, trace_id, request_id)

                    return response

                finally:
                    context.detach(token)

            except Exception as exc:
                # Record error metrics and span
                self._record_error_metrics(request, exc, start_time)
                self._finalize_error_span(span, request, exc, start_time)
                raise

            finally:
                span.end()

    def _get_trace_id(self, request: Request) -> str:
        """Extract trace_id from headers or generate new one."""

        # Check multiple possible header variations
        header_keys = [
            "x-trace-id",
            "trace-id",
            "x-correlation-id",
            "correlation-id",
            "traceparent",
        ]

        for header_key in header_keys:
            value = request.headers.get(header_key)
            if value:
                try:
                    # For traceparent, extract trace ID part
                    if header_key == "traceparent":
                        parts = value.split("-")
                        if len(parts) >= 2:
                            return parts[1]
                    return str(value)

                except (ValueError, IndexError):
                    continue

        return str(uuid.uuid4())

    def _should_skip_tracing(self, request: Request) -> bool:
        """Determine if request should be traced."""

        skip_paths = {
            "/v1/health",
            "/v1/metrics",
            "/v1/docs",
            "/v1/redoc",
            "/v1/docs/openapi.json",
            "/favicon.ico",
        }

        return request.url.path in skip_paths or request.url.path.startswith("/static/")

    def _set_span_attributes(
        self, span: Span, request: Request, trace_id: str, request_id: str
    ) -> None:
        """Set comprehensive span attributes."""

        # HTTP attributes
        span.set_attribute("http.method", request.method)
        span.set_attribute("http.url", str(request.url))
        span.set_attribute("http.scheme", request.url.scheme)
        span.set_attribute("http.host", request.url.hostname or "unknown")
        span.set_attribute("http.target", request.url.path)
        span.set_attribute("http.user_agent", request.headers.get("user-agent", ""))

        # Custom attributes
        span.set_attribute("custom.trace_id", trace_id)
        span.set_attribute("custom.request_id", request_id)
        span.set_attribute("custom.client_ip", self._get_client_ip(request))

        # Query parameters (sanitized)
        if request.query_params:
            for key, value in request.query_params.items():
                if not self._is_sensitive_param(key):
                    span.set_attribute(f"http.query.{key}", str(value)[:100])

    def _finalize_successful_span(
        self, span: Span, _request: Request, response: Response, start_time: float
    ) -> None:
        """Finalize span for successful requests."""

        duration_ms = (time.time() - start_time) * 1000

        span.set_attribute("http.status_code", response.status_code)
        span.set_attribute(
            "http.response.size", int(response.headers.get("content-length", 0))
        )
        span.set_attribute("custom.duration_ms", round(duration_ms, 2))

        # Set span status
        if response.status_code >= 400:
            span.set_status(Status(StatusCode.ERROR, f"HTTP {response.status_code}"))
        else:
            span.set_status(Status(StatusCode.OK))

    def _finalize_error_span(
        self, span: Span, _request: Request, exception: Exception, start_time: float
    ) -> None:
        """Finalize span for failed requests."""

        duration_ms = (time.time() - start_time) * 1000

        span.set_attribute("custom.duration_ms", round(duration_ms, 2))
        span.set_attribute("error", True)
        span.set_attribute("error.type", type(exception).__name__)
        span.set_attribute("error.message", str(exception)[:500])

        # Record exception
        span.record_exception(exception)
        span.set_status(Status(StatusCode.ERROR, str(exception)))

    def _record_success_metrics(
        self, request: Request, response: Response, start_time: float
    ) -> None:
        """Record metrics for successful requests."""

        duration_ms = (time.time() - start_time) * 1000

        labels = {
            "method": request.method,
            "endpoint": request.url.path,
            "status_code": str(response.status_code),
            "status_class": f"{response.status_code // 100}xx",
        }

        self.request_duration.record(duration_ms, labels)
        self.request_counter.add(1, labels)

    def _record_error_metrics(
        self, request: Request, exception: Exception, start_time: float
    ) -> None:
        """Record metrics for failed requests."""

        duration_ms = (time.time() - start_time) * 1000

        labels = {
            "method": request.method,
            "endpoint": request.url.path,
            "status_code": "500",
            "status_class": "5xx",
            "error_type": type(exception).__name__,
        }

        self.request_duration.record(duration_ms, labels)
        self.request_counter.add(1, labels)

    def _add_trace_headers(
        self, response: Response, trace_id: str, request_id: str
    ) -> None:
        """Add tracing and security headers to response."""

        # Tracing headers
        response.headers["X-Trace-ID"] = trace_id
        response.headers["X-Request-ID"] = request_id

        # Inject OpenTelemetry context for downstream services
        carrier = {}
        inject(carrier)
        for key, value in carrier.items():
            response.headers[f"X-OTel-{key}"] = value

        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address."""

        ClientIPExtractor.extract_client_ip(request)

    def _is_sensitive_param(self, key: str) -> bool:
        """Check if query parameter contains sensitive data."""

        sensitive_patterns = {
            "password",
            "secret",
            "token",
            "key",
            "auth",
            "credential",
            "api_key",
            "access_token",
        }

        return any(pattern in key.lower() for pattern in sensitive_patterns)
