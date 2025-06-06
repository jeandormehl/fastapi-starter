from fastapi import FastAPI
from fastapi.middleware import cors, gzip, trustedhost

from ...core.config import Configuration
from .error_middleware import ErrorMiddleware
from .logging_middleware import LoggingMiddleware
from .tracing_middleware import TracingMiddleware

__all__ = [
    "ErrorMiddleware",
    "LoggingMiddleware",
    "TracingMiddleware",
    "register_request_middlewares",
]

from .request_logging_middleware import RequestLoggingMiddleware


def register_request_middlewares(config: Configuration, app: FastAPI) -> None:
    """Register all request middlewares in correct order.

    Middleware execution order is reverse of registration order:
    1. TracingMiddleware (outermost - establishes context)
    2. LoggingMiddleware (middle - logs with context)
    3. ErrorMiddleware (innermost - catches errors)
    4. RequestLoggingMiddleware (
            innermost - captures request/response state including errors
        )
    """

    # Register in reverse order of desired execution
    # RequestLoggingMiddleware runs last to capture everything including errors
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(ErrorMiddleware)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(TracingMiddleware)
    app.add_middleware(
        trustedhost.TrustedHostMiddleware, allowed_hosts=config.api_allowed_hosts
    )
    app.add_middleware(
        cors.CORSMiddleware,
        allow_origins=config.api_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(gzip.GZipMiddleware, minimum_size=1000)
