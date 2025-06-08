from datetime import datetime
from enum import Enum
from typing import Any

from fastapi import status
from kink import di
from pydantic import BaseModel


class ErrorSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class StandardErrorResponse(BaseModel):
    """Standardized error response format across the entire domain."""

    error: str
    message: str
    code: str
    details: dict[str, Any] | None = None
    timestamp: str
    trace_id: str | None = None
    request_id: str | None = None
    severity: ErrorSeverity = ErrorSeverity.MEDIUM

    @classmethod
    def create(
        cls,
        error: str,
        message: str,
        code: str,
        details: dict[str, Any] | None = None,
        trace_id: str | None = None,
        request_id: str | None = None,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
    ) -> "StandardErrorResponse":
        return cls(
            error=error,
            message=message,
            code=code,
            details=details or {},
            timestamp=datetime.now(di["timezone"]).isoformat(),
            trace_id=trace_id,
            request_id=request_id,
            severity=severity,
        )


class ErrorResponseBuilder:
    """Builder for creating standardized error responses."""

    @staticmethod
    def validation_error(
        message: str,
        details: dict[str, Any] | None = None,
        trace_id: str | None = None,
        request_id: str | None = None,
    ) -> StandardErrorResponse:
        return StandardErrorResponse.create(
            error="validation error",
            message=message,
            code="validation_error",
            details=details,
            trace_id=trace_id,
            request_id=request_id,
            severity=ErrorSeverity.LOW,
        )

    @staticmethod
    def authentication_error(
        message: str = "authentication required",
        trace_id: str | None = None,
        request_id: str | None = None,
    ) -> StandardErrorResponse:
        return StandardErrorResponse.create(
            error="authentication error",
            message=message,
            code="authentication_error",
            trace_id=trace_id,
            request_id=request_id,
            severity=ErrorSeverity.MEDIUM,
        )

    @staticmethod
    def authorization_error(
        message: str = "insufficient permissions",
        trace_id: str | None = None,
        request_id: str | None = None,
    ) -> StandardErrorResponse:
        return StandardErrorResponse.create(
            error="authorization error",
            message=message,
            code="authorization_error",
            trace_id=trace_id,
            request_id=request_id,
            severity=ErrorSeverity.MEDIUM,
        )

    @staticmethod
    def not_found_error(
        resource: str, trace_id: str | None = None, request_id: str | None = None
    ) -> StandardErrorResponse:
        return StandardErrorResponse.create(
            error="resource not found",
            message=f"{resource} not found",
            code="not_found",
            trace_id=trace_id,
            request_id=request_id,
            severity=ErrorSeverity.LOW,
        )

    @staticmethod
    def internal_server_error(
        message: str = "internal server error occurred",
        details: dict[str, Any] | None = None,
        trace_id: str | None = None,
        request_id: str | None = None,
    ) -> StandardErrorResponse:
        return StandardErrorResponse.create(
            error="internal server error",
            message=message,
            code="internal_server_error",
            details=details,
            trace_id=trace_id,
            request_id=request_id,
            severity=ErrorSeverity.CRITICAL,
        )

    @staticmethod
    def rate_limit_error(
        message: str = "rate limit exceeded",
        retry_after: int | None = None,
        trace_id: str | None = None,
        request_id: str | None = None,
    ) -> StandardErrorResponse:
        details = {"retry_after_seconds": retry_after} if retry_after else None
        return StandardErrorResponse.create(
            error="rate limit exceeded",
            message=message,
            code="rate_limit_exceeded",
            details=details,
            trace_id=trace_id,
            request_id=request_id,
            severity=ErrorSeverity.MEDIUM,
        )


def create_error_response_json(
    error_response: StandardErrorResponse,
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
) -> dict[str, Any]:
    """Create JSON response dict from StandardErrorResponse."""

    return {
        "status_code": status_code,
        "content": error_response.model_dump_json(),
        "headers": {
            "X-Trace-ID": error_response.trace_id or "unknown",
            "X-Request-ID": error_response.request_id or "unknown",
            "X-Error-Code": error_response.code,
        },
    }
