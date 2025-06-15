from typing import Any

from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.trace import Span
from starlette.types import ASGIApp

from app.common.logging import get_logger
from app.core.config.otel_config import OtelConfiguration


def setup_instrumentations(app: ASGIApp, config: OtelConfiguration) -> None:
    """Setup automatic instrumentations with improved error handling."""
    if not config.enabled:
        get_logger(__name__).info("otel instrumentation disabled by configuration")
        return

    instrumentations = []

    try:
        # FastAPI Instrumentation
        if config.instrument_fastapi:
            FastAPIInstrumentor.instrument_app(
                app,
                excluded_urls="health,metrics,docs,openapi.json,favicon.ico",
                server_request_hook=_server_request_hook
                if config.capture_request_body
                else None,
                client_response_hook=_client_response_hook
                if config.capture_response_body
                else None,
            )
            instrumentations.append("FastAPI")

        # Redis Instrumentation
        if config.instrument_redis:
            try:
                RedisInstrumentor().instrument()
                instrumentations.append("Redis")

            except Exception as e:
                get_logger(__name__).warning(f"failed to instrument Redis: {e}")

        # HTTP Requests Instrumentation
        if config.instrument_requests:
            try:
                HTTPXClientInstrumentor().instrument()
                instrumentations.append("HTTPX")
            except Exception as e:
                get_logger(__name__).warning(f"failed to instrument HTTPX: {e}")

        # Logging Instrumentation
        if config.instrument_logging:
            try:
                LoggingInstrumentor().instrument()
                instrumentations.append("Logging")

            except Exception as e:
                get_logger(__name__).warning(f"failed to instrument logging: {e}")

        if instrumentations:
            get_logger(__name__).info(
                f"otel instrumentations enabled: {', '.join(instrumentations)}"
            )

    except Exception as e:
        get_logger(__name__).error(f"failed to setup instrumentations: {e}")


def _server_request_hook(span: Span, scope: Any) -> None:
    """Hook to capture additional request data with error handling."""
    try:
        if scope.get("type") == "http":
            # Add custom attributes safely
            path = scope.get("path", "")
            method = scope.get("method", "")

            if path:
                span.set_attribute("custom.request.path", path[:200])
            if method:
                span.set_attribute("custom.request.method", method)

    except Exception as e:
        get_logger(__name__).debug(f"error in server request hook: {e}")


# noinspection PyUnusedLocal
def _client_response_hook(span: Span, scope: Any, message: Any) -> None:  # noqa: ARG001
    """Hook to capture additional response data with error handling."""
    try:
        if message.get("type") == "http.response.start":
            status_code = message.get("status", 0)
            if status_code:
                span.set_attribute("custom.response.status_code", status_code)

    except Exception as e:
        get_logger(__name__).debug(f"error in client response hook: {e}")
