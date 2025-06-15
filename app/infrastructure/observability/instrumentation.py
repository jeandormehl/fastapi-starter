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
    """Setup automatic instrumentations for third-party libraries."""

    logger = get_logger(__name__)
    if not config.enabled:
        return

    try:
        # FastAPI Instrumentation
        if config.instrument_fastapi:
            FastAPIInstrumentor.instrument_app(
                app,
                excluded_urls="health,metrics,docs,openapi.json",
                server_request_hook=(
                    _server_request_hook if config.capture_request_body else None
                ),
                client_response_hook=(
                    _client_response_hook if config.capture_response_body else None
                ),
            )
            logger.info("app instrumentation enabled")

        # Redis Instrumentation
        if config.instrument_redis:
            RedisInstrumentor().instrument()
            logger.info("redis instrumentation enabled")

        # HTTP Requests Instrumentation
        if config.instrument_requests:
            HTTPXClientInstrumentor().instrument()
            logger.info("httpx instrumentation enabled")

        # Logging Instrumentation
        if config.instrument_logging:
            LoggingInstrumentor().instrument()
            logger.info("logging instrumentation enabled")

    except Exception as e:
        logger.error(f"failed to setup instrumentations: {e}")


def _server_request_hook(span: Span, scope: Any) -> None:
    """Hook to capture additional request data."""

    logger = get_logger(__name__)
    try:
        if scope.get("type") == "http":
            # Add custom attributes
            span.set_attribute("custom.request.path", scope.get("path", ""))
            span.set_attribute("custom.request.method", scope.get("method", ""))

    except Exception as e:
        logger.debug(f"error in server request hook: {e}")


# noinspection PyUnusedLocal
def _client_response_hook(span: Span, scope: Any, message: Any) -> None:  # noqa: ARG001
    """Hook to capture additional response data."""

    logger = get_logger(__name__)
    try:
        if message.get("type") == "http.response.start":
            status_code = message.get("status", 0)
            span.set_attribute("custom.response.status_code", status_code)

    except Exception as e:
        logger.debug(f"error in client response hook: {e}")
