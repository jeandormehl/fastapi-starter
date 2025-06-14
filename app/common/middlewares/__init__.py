from fastapi import FastAPI
from fastapi.middleware import cors, gzip, trustedhost

from app.core.config import Configuration

from .error_middleware import ErrorMiddleware
from .idempotency_middleware import IdempotencyMiddleware
from .logging_middleware import LoggingMiddleware
from .tracing_middleware import TracingMiddleware

__all__ = [
    "ErrorMiddleware",
    "LoggingMiddleware",
    "TracingMiddleware",
    "register_request_middlewares",
]


def register_request_middlewares(config: Configuration, app: FastAPI) -> None:
    """Register all request middlewares in correct order.

    Middleware execution order is reverse of registration order:
    1. TracingMiddleware (outermost - establishes context)
    2. IdempotencyMiddleware (middle)
    2. LoggingMiddleware (middle - logs with context)
    3. ErrorMiddleware (innermost - catches errors)
    """

    # Register in reverse order of desired execution
    app.add_middleware(ErrorMiddleware)

    if config.idempotency.enabled and config.idempotency.request_enabled:
        app.add_middleware(IdempotencyMiddleware)

    app.add_middleware(LoggingMiddleware)
    app.add_middleware(TracingMiddleware)
    app.add_middleware(
        trustedhost.TrustedHostMiddleware, allowed_hosts=config.api.allowed_hosts
    )
    app.add_middleware(
        cors.CORSMiddleware,
        allow_origins=config.api.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(gzip.GZipMiddleware, minimum_size=1000)
