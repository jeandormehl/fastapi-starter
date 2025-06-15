import contextlib
import time
import uuid
from typing import Any

from fastapi import Request
from opentelemetry import context, trace
from opentelemetry.propagate import extract
from opentelemetry.trace import Span, Status, StatusCode
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp

from app.common.logging import get_logger
from app.common.utils import ClientIPExtractor
from app.infrastructure.observability.metrics import get_meter
from app.infrastructure.observability.tracing import get_tracer


class TracingMiddleware(BaseHTTPMiddleware):
    """Optimized middleware for request tracing with full OpenTelemetry integration."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

        self.tracer = get_tracer("fastapi.requests", "1.0.0")
        self.meter = get_meter("fastapi.requests", "1.0.0")

        # Initialize metrics with error handling
        self.request_duration = None
        self.request_counter = None

        self.logger = get_logger(__name__)

        try:
            self.request_duration = self.meter.create_histogram(
                name="http_request_duration_seconds",
                description="HTTP request duration in seconds",
                unit="s",
            )
            self.request_counter = self.meter.create_counter(
                name="http_requests_total",
                description="Total number of HTTP requests",
            )

        except Exception as e:
            self.logger.warning(f"failed to create metrics: {e}")

    # noinspection PyUnreachableCode
    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Process request with optimized tracing context setup."""

        # Skip tracing for health/metrics endpoints
        if self._should_skip_tracing(request):
            return await call_next(request)

        # Extract or generate trace context
        trace_id = self._extract_trace_id(request)
        request_id = str(uuid.uuid4())

        # Store trace information in request state
        request.state.trace_id = trace_id
        request.state.request_id = request_id

        # Extract OpenTelemetry context from headers
        carrier = dict(request.headers)
        otel_context = extract(carrier)

        start_time = time.time()

        # Create span with extracted context
        with context.attach(otel_context):
            span_name = f"{request.method} {self._normalize_path(request.url.path)}"
            span = self.tracer.start_span(span_name, kind=trace.SpanKind.SERVER)

            # Set span attributes
            self._set_span_attributes(span, request, trace_id, request_id)

            # Store span and context in request state
            request.state.otel_span = span
            request.state.otel_context = context.get_current()

            try:
                # Make span current and process request
                with trace.use_span(span):
                    response = await call_next(request)

                    # Record successful request
                    self._record_success_metrics(request, response, start_time)
                    self._finalize_successful_span(span, response, start_time)

                    # Add tracing headers to response
                    self._add_trace_headers(response, trace_id, request_id, span)

                    return response

            except Exception as exc:
                # Record error metrics and span
                self._record_error_metrics(request, exc, start_time)
                self._finalize_error_span(span, exc, start_time)
                raise
            finally:
                span.end()

    def _extract_trace_id(self, request: Request) -> str:
        """Extract trace_id from headers with fallback logic."""

        # Check multiple possible header variations
        header_keys = ["x-trace-id", "trace-id", "x-correlation-id", "correlation-id"]

        for header_key in header_keys:
            value = request.headers.get(header_key)
            if value:
                return str(value)

        # Extract from traceparent header
        traceparent = request.headers.get("traceparent")
        if traceparent:
            try:
                parts = traceparent.split("-")
                if len(parts) >= 2 and len(parts[1]) == 32:
                    return parts[1]
            except (ValueError, IndexError):
                contextlib.suppress(ValueError, IndexError)

        return str(uuid.uuid4())

    def _normalize_path(self, path: str) -> str:
        """Normalize path for better span naming with caching."""

        import re

        # Replace UUID patterns
        path = re.sub(
            r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            "/{uuid}",
            path,
            flags=re.IGNORECASE,
        )

        # Replace numeric IDs
        return re.sub(r"/\d+", "/{id}", path)

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

        path = request.url.path
        return path in skip_paths or path.startswith("/static/")

    def _set_span_attributes(
        self, span: Span, request: Request, trace_id: str, request_id: str
    ) -> None:
        """Set comprehensive span attributes with error handling."""

        try:
            # HTTP semantic conventions
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.url", str(request.url)[:500])  # Limit length
            span.set_attribute("http.scheme", request.url.scheme)
            span.set_attribute("http.host", request.url.hostname or "unknown")
            span.set_attribute("http.target", request.url.path[:200])
            span.set_attribute(
                "http.user_agent", request.headers.get("user-agent", "")[:200]
            )

            # Custom attributes
            span.set_attribute("custom.trace_id", trace_id)
            span.set_attribute("custom.request_id", request_id)

            # Client information
            with contextlib.suppress(Exception):
                client_ip = ClientIPExtractor.extract_client_ip(request)
                span.set_attribute("http.client_ip", client_ip)

            # Query parameters (sanitized and limited)
            if request.query_params:
                for i, (key, value) in enumerate(request.query_params.items()):
                    if i >= 10:  # Limit to 10 params
                        break
                    if not self._is_sensitive_param(key):
                        span.set_attribute(f"http.query.{key}", str(value)[:100])

        except Exception as e:
            self.logger.debug(f"failed to set span attributes: {e}")

    def _finalize_successful_span(
        self, span: Span, response: Response, start_time: float
    ) -> None:
        """Finalize span for successful requests with better error handling."""

        try:
            duration_ms = (time.time() - start_time) * 1000

            span.set_attribute("http.status_code", response.status_code)

            content_length = response.headers.get("content-length")
            if content_length:
                with contextlib.suppress(ValueError):
                    span.set_attribute("http.response.size", int(content_length))

            span.set_attribute("duration_ms", round(duration_ms, 2))

            # Set span status
            if response.status_code >= 400:
                span.set_status(
                    Status(StatusCode.ERROR, f"HTTP {response.status_code}")
                )
            else:
                span.set_status(Status(StatusCode.OK))

        except Exception as e:
            self.logger.debug(f"failed to finalize successful span: {e}")

    def _finalize_error_span(
        self, span: Span, exception: Exception, start_time: float
    ) -> None:
        """Finalize span for failed requests with improved error handling."""

        try:
            duration_ms = (time.time() - start_time) * 1000

            span.set_attribute("duration_ms", round(duration_ms, 2))
            span.set_attribute("error", True)
            span.set_attribute("error.type", type(exception).__name__)
            span.set_attribute("error.message", str(exception)[:500])

            # Record exception
            span.record_exception(exception)
            span.set_status(Status(StatusCode.ERROR, str(exception)[:200]))

        except Exception as e:
            self.logger.debug(f"failed to finalize error span: {e}")

    def _record_success_metrics(
        self, request: Request, response: Response, start_time: float
    ) -> None:
        """Record metrics for successful requests with error handling."""

        if not self.request_duration or not self.request_counter:
            return

        try:
            duration_seconds = time.time() - start_time

            labels = {
                "method": request.method,
                "endpoint": self._normalize_path(request.url.path),
                "status_code": str(response.status_code),
                "status_class": f"{response.status_code // 100}xx",
            }

            self.request_duration.record(duration_seconds, labels)
            self.request_counter.add(1, labels)

        except Exception as e:
            self.logger.debug(f"failed to record success metrics: {e}")

    def _record_error_metrics(
        self, request: Request, exception: Exception, start_time: float
    ) -> None:
        """Record metrics for failed requests with error handling."""

        if not self.request_duration or not self.request_counter:
            return

        try:
            duration_seconds = time.time() - start_time

            labels = {
                "method": request.method,
                "endpoint": self._normalize_path(request.url.path),
                "status_code": "500",
                "status_class": "5xx",
                "error_type": type(exception).__name__,
            }

            self.request_duration.record(duration_seconds, labels)
            self.request_counter.add(1, labels)

        except Exception as e:
            self.logger.debug(f"failed to record error metrics: {e}")

    def _add_trace_headers(
        self, response: Response, trace_id: str, request_id: str, span: Span
    ) -> None:
        """Add tracing headers to response with error handling."""

        try:
            # Standard tracing headers
            response.headers["X-Trace-ID"] = trace_id
            response.headers["X-Request-ID"] = request_id

            # OpenTelemetry span context
            span_context = span.get_span_context()
            if span_context.is_valid:
                response.headers["X-OTel-Trace-ID"] = format(
                    span_context.trace_id, "032x"
                )
                response.headers["X-OTel-Span-ID"] = format(
                    span_context.span_id, "016x"
                )

        except Exception as e:
            self.logger.debug(f"failed to add trace headers: {e}")

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
