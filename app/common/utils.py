import base64
import json
from typing import Any

from fastapi.requests import Request
from prisma import Json
from pydantic import BaseModel

from app.common.base_handler import TRequest, TResponse
from app.common.constants import MODEL_JSON_FIELDS
from app.common.errors.errors import ApplicationError, ErrorCode


class PydiatorBuilder:
    """Builds Pydiator request or response with proper trace context."""

    @classmethod
    def build(
        cls,
        cls_type: type[TRequest | TResponse],
        req: Request | None = None,
        **kwargs: str | int | bool | dict | BaseModel | None,
    ) -> TRequest | TResponse:
        # Extract trace information with fallbacks
        if isinstance(req, Request):
            trace_id = getattr(req.state, "trace_id", None)
            request_id = getattr(req.state, "request_id", None)

        else:
            trace_id = kwargs.get("trace_id")
            request_id = kwargs.get("request_id")

        if not trace_id or not request_id:
            raise ApplicationError(
                ErrorCode.VALIDATION_ERROR,
                "no 'trace_id' or 'request_id' set for operation",
            )

        data = {
            "trace_id": trace_id,
            "request_id": request_id,
            "req": req,
            **kwargs,
        }

        return cls_type(**data)


class DataSanitizer:
    """Centralized data sanitization for logs and responses."""

    @classmethod
    def sanitize_data(cls, data: Any, max_length: int = 10000) -> Any:
        """Recursively sanitize sensitive data."""

        if isinstance(data, dict):
            sanitized_dict = {}

            for key, value in data.items():
                if cls._is_sensitive_key(key):
                    if key in ["auth_method", "token_type"]:
                        continue
                    if isinstance(value, dict):
                        sanitized_dict[key] = cls.sanitize_data(value, max_length)
                        break
                    if isinstance(value, list | tuple):
                        sanitized_dict[key] = cls._redact_inner(value)
                    if isinstance(value, bool):
                        sanitized_dict[key] = value
                    else:
                        sanitized_dict[key] = "[REDACTED]"
                else:
                    sanitized_dict[key] = cls.sanitize_data(value, max_length)
            return sanitized_dict

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
    def _redact_inner(cls, data: Any) -> Any:
        """Recursively redacts all values within a given data structure."""
        if isinstance(data, dict):
            return dict.fromkeys(data, "[REDACTED]")
        if isinstance(data, list | tuple):
            return ["[REDACTED]" for _ in data]
        return "[REDACTED]"

    @classmethod
    def sanitize_headers(cls, headers: dict[str, Any]) -> dict[str, str]:
        """Sanitize headers removing sensitive information and fixing key formatting."""

        safe_headers = {}
        for key, value in headers.items():
            # Replace hyphens with underscores to prevent GraphQL parsing issues
            safe_key = key.replace("-", "_")
            if cls._is_sensitive_key(key):
                safe_headers[safe_key] = "[REDACTED]"
            else:
                safe_headers[safe_key] = str(value)
        return safe_headers


class ClientIPExtractor:
    """Utility for extracting client IP addresses."""

    @staticmethod
    def extract_client_ip(request: Request) -> str:
        """Extract client IP with proper proxy support."""

        # Check for forwarded headers first
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # Get first IP from comma-separated list
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

        # List of common binary content types
        binary_types = [
            "image/png",
            "image/jpeg",
            "image/gif",
            "application/octet-stream",
            "application/pdf",
            "audio/mpeg",
            "video/mp4",
        ]

        # 1. Prioritize binary handling if body_type indicates binary content
        if body_type.lower() in binary_types:
            content = base64.b64encode(body).decode("ascii")
            if len(body) > max_size:
                return {
                    "truncated": True,
                    "original_size": len(body),
                    "captured_size": max_size,
                    "type": "binary",
                    "content": base64.b64encode(body[:max_size]).decode("ascii")
                    + "...",
                    "encoding": "base64",
                }
            return {
                "content": content,
                "type": "binary",
                "size": len(body),
                "encoding": "base64",
            }

        # Handle truncation for non-binary types before attempting decoding
        if len(body) > max_size:
            return {
                "truncated": True,
                "original_size": len(body),
                "captured_size": max_size,
                "type": body_type,  # Keep original body_type for truncated text/json
                "content": BodyProcessor._truncate_body_safely(body, max_size),
            }

        # Try JSON parsing
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

        # Fallback to base64 for any remaining undecodable data
        # (should ideally be caught by binary_types check)
        return {
            "content": base64.b64encode(body).decode("ascii"),
            "type": "binary",
            "size": len(body),
            "encoding": "base64",
        }

    @staticmethod
    def _truncate_body_safely(body: bytes, max_size: int) -> str:
        """Truncate body content safely for display."""

        # This is a simplified truncation. For actual binary, you might
        # still want to base64 encode the truncated part.
        try:
            # Try to decode if it's likely text
            return body[:max_size].decode("utf-8", errors="ignore") + "..."

        except UnicodeDecodeError:
            # If not text, represent as hex or base64 of the truncated part
            return base64.b64encode(body[:max_size]).decode("ascii") + "..."


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


class PrismaDataTransformer:
    """
    Utility class for transforming Pydantic model data for Prisma consumption.

    Handles the conversion of dict/list fields to Json objects for Json-type
    fields in Prisma schema.
    """

    @classmethod
    def prepare_data(cls, data: dict[str, Any], model_name: str) -> dict[str, Any]:
        json_fields = MODEL_JSON_FIELDS.get(model_name, set())

        if not json_fields:
            return data

        prepared_data = data.copy()

        for field in json_fields:
            if prepared_data[field] is None:
                prepared_data[field] = Json(None)
                continue
            if (
                field in prepared_data and prepared_data[field] is not None
            ) and isinstance(prepared_data[field], dict | list):
                prepared_data[field] = Json(prepared_data[field])

        return prepared_data
