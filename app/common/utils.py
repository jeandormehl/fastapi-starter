import base64
import json
import uuid
from typing import Any, TypeVar

from fastapi.requests import Request

from app.common import BaseRequest

T = TypeVar("T", bound=BaseRequest)


async def build_pydiator_request(
    request_class: type[T], req: Request, **kwargs: str | int | bool | dict | None
) -> T:
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

    return request_class(**request_data)


class DataSanitizer:
    """Centralized data sanitization for logs and responses."""

    @classmethod
    def sanitize_data(cls, data: Any, max_length: int = 1000) -> Any:
        """Recursively sanitize sensitive data."""

        if isinstance(data, dict):
            return {
                key: "[REDACTED]"
                if cls._is_sensitive_key(key)
                else cls.sanitize_data(value, max_length)
                for key, value in data.items()
            }

        if isinstance(data, list | tuple):
            return [cls.sanitize_data(item, max_length) for item in data]

        if isinstance(data, str) and len(data) > max_length:
            return data[:max_length] + "...[TRUNCATED]"

        return data

    @classmethod
    def _is_sensitive_key(cls, key: str) -> bool:
        """Check if key contains sensitive information."""

        from app.common.constants import SENSITIVE_PATTERNS

        key_lower = key.lower()
        return any(pattern in key_lower for pattern in SENSITIVE_PATTERNS)

    @classmethod
    def sanitize_headers(cls, headers: dict[str, Any]) -> dict[str, str]:
        """Sanitize HTTP headers removing sensitive information."""

        safe_headers = {}
        for key, value in headers.items():
            if cls._is_sensitive_key(key):
                safe_headers[key] = "[REDACTED]"
            else:
                safe_headers[key] = str(value)
        return safe_headers


class ClientIPExtractor:
    """Utility for extracting client IP addresses."""

    @staticmethod
    def extract_client_ip(request: Request) -> str:
        """Extract client IP with proper proxy support"""

        # Check for forwarded headers first
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # FIX: Get first IP from comma-separated list
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()

        # Fallback to direct client
        return request.client.host if request.client else "unknown"


class BodyProcessor:
    """Utility for processing request/response bodies."""

    @staticmethod
    def process_body_content(
        body: bytes, body_type: str, max_size: int = 10000
    ) -> dict[str, Any]:
        """Process and format body content with size limits."""

        if len(body) > max_size:
            return {
                "truncated": True,
                "original_size": len(body),
                "captured_size": max_size,
                "type": body_type,
                "content": BodyProcessor._truncate_body_safely(body, max_size),
            }

        # Try JSON parsing first
        try:
            content = json.loads(body.decode("utf-8"))

            return {
                "content": content,
                "type": "json",
                "size": len(body),
                "encoding": "utf-8",
            }

        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

        # Try text decoding with multiple encodings
        for encoding in ["utf-8", "utf-16", "latin1"]:
            try:
                content = body.decode(encoding)

                return {
                    "content": content,
                    "type": "text",
                    "size": len(body),
                    "encoding": encoding,
                }

            except UnicodeDecodeError:
                continue

        # Fallback to base64 for binary data
        return {
            "content": base64.b64encode(body).decode("ascii"),
            "type": "binary",
            "size": len(body),
            "encoding": "base64",
        }

    @staticmethod
    def _truncate_body_safely(body: bytes, max_size: int) -> str:
        """Safely truncate body content without breaking encoding."""

        truncated = body[:max_size]

        try:
            return truncated.decode("utf-8")

        except UnicodeDecodeError:
            # Remove potentially broken bytes at the end
            for i in range(min(4, len(truncated))):
                try:
                    return truncated[: -i - 1].decode("utf-8") + "..."

                except UnicodeDecodeError:
                    continue

            # Final fallback
            return base64.b64encode(truncated).decode("ascii")


class TraceContextExtractor:
    """Utility for extracting trace context information."""

    @staticmethod
    def get_trace_id(request: Request) -> str:
        """Safely extract trace ID from request state."""

        if hasattr(request, "state") and hasattr(request.state, "trace_id"):
            trace_id = getattr(request.state, "trace_id", None)

            if trace_id:
                return str(trace_id)
        return "unknown"

    @staticmethod
    def get_request_id(request: Request) -> str:
        """Safely extract request ID from request state."""

        if hasattr(request, "state") and hasattr(request.state, "request_id"):
            request_id = getattr(request.state, "request_id", None)

            if request_id:
                return str(request_id)
        return "unknown"
