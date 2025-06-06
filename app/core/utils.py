import uuid
from typing import TypeVar

from fastapi.requests import Request

from app.common import BaseRequest

T = TypeVar("T", bound=BaseRequest)


async def build_pydiator_request(
    request_class: type[T], req: Request, **kwargs: str | int | bool | dict | None
) -> T:
    """
    Utility to build pydiator requests with
    comprehensive error handling support.
    """

    # Extract trace information with fallbacks
    trace_id = getattr(req.state, "trace_id", None)
    if not isinstance(trace_id, str):
        trace_id = str(uuid.uuid4())

    request_id = getattr(req.state, "request_id", None)
    if not isinstance(request_id, str):
        request_id = str(uuid.uuid4())

    request_data = {
        "trace_id": trace_id,
        "request_id": request_id,
        "req": req,
        **kwargs,
    }

    try:
        return request_class(**request_data)
    except Exception as exc:
        # Log request building failure
        from app.core.logging import get_logger

        logger = get_logger(__name__)
        logger.bind(
            trace_id=trace_id,
            request_id=request_id,
            request_class=request_class.__name__,
            exception_type=type(exc).__name__,
            exception_message=str(exc),
        ).error("failed to build pydiator request")

        raise


def extract_client_info(request: Request) -> dict[str, str]:
    """Extract client information from request for logging."""

    return {
        "client_ip": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("user-agent", "unknown"),
        "referer": request.headers.get("referer", "unknown"),
        "accept_language": request.headers.get("accept-language", "unknown"),
        "content_type": request.headers.get("content-type", "unknown"),
    }


def sanitize_for_logging(data: dict) -> dict:
    """Sanitize sensitive data for logging purposes."""

    sensitive_keys = {
        "password",
        "token",
        "secret",
        "key",
        "authorization",
        "auth",
        "credential",
        "pwd",
        "pass",
    }

    sanitized = {}
    for key, value in data.items():
        if any(sensitive in key.lower() for sensitive in sensitive_keys):
            sanitized[key] = "[REDACTED]"
        elif isinstance(value, dict):
            sanitized[key] = sanitize_for_logging(value)
        else:
            sanitized[key] = value

    return sanitized
