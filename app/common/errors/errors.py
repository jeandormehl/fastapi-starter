from enum import Enum
from typing import Any

from fastapi import status
from kink import di
from pydantic import BaseModel


class ErrorCode(Enum):
    """Standardized error codes for the application."""

    # General errors (1000-1999)
    INTERNAL_SERVER_ERROR = "ERR_1000"
    VALIDATION_ERROR = "ERR_1001"
    AUTHENTICATION_ERROR = "ERR_1002"
    AUTHORIZATION_ERROR = "ERR_1003"
    CONFIGURATION_ERROR = "ERR_1004"
    RATE_LIMIT_EXCEEDED = "ERR_1005"

    # Resource errors (2000-2999)
    RESOURCE_NOT_FOUND = "ERR_2000"
    RESOURCE_ALREADY_EXISTS = "ERR_2001"
    RESOURCE_CONFLICT = "ERR_2002"

    # Business logic errors (3000-3999)
    BUSINESS_RULE_VIOLATION = "ERR_3000"
    INSUFFICIENT_PERMISSIONS = "ERR_3001"
    INVALID_STATE_TRANSITION = "ERR_3002"

    # External service errors (4000-4999)
    EXTERNAL_SERVICE_ERROR = "ERR_4000"
    EXTERNAL_SERVICE_TIMEOUT = "ERR_4001"
    EXTERNAL_SERVICE_UNAVAILABLE = "ERR_4002"

    # Data errors (5000-5999)
    DATABASE_ERROR = "ERR_5000"
    DATABASE_CONNECTION = "ERR_5001"

    # Client errors (6000-6999)
    CLIENT_INACTIVE = "ERR_6000"
    CLIENT_NOT_FOUND = "ERR_6001"
    INVALID_CREDENTIALS = "ERR_6002"

    # Token errors (7000-7999)
    TOKEN_EXPIRED = "ERR_7000"  # nosec
    TOKEN_INVALID = "ERR_7001"  # nosec

    # Scope errors (8000-8999)
    SCOPE_NOT_FOUND = "ERR_8000"

    # Task errors (9000-9999)
    TASK_EXECUTION_ERROR = "ERR_9000"
    TASK_QUARANTINED = "ERR_9001"
    TASK_RATE_LIMITED = "ERR_9002"


class ErrorDetail(BaseModel):
    """Standardized error detail structure."""

    trace_id: str | None = None
    request_id: str | None = None
    code: str
    message: str
    timestamp: str | None = None
    details: dict[str, Any] = {}


class ApplicationError(Exception):
    """Base application exception with standardized error handling."""

    def __init__(
        self,
        error_code: ErrorCode,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict[str, Any] | None = None,
        trace_id: str | None = None,
        request_id: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        self.trace_id = trace_id
        self.request_id = request_id
        self.cause = cause

        # Add cause information to details if provided
        if cause:
            self.details.update(
                {
                    "caused_by": type(cause).__name__,
                    "cause_message": str(cause),
                }
            )

        super().__init__(message)

    def to_error_detail(self) -> ErrorDetail:
        """Convert exception to standardized error detail."""

        from datetime import datetime

        return ErrorDetail(
            code=self.error_code.value,
            message=self.message,
            details=self.details,
            timestamp=datetime.now(di["timezone"]).isoformat(),
            trace_id=self.trace_id,
            request_id=self.request_id,
        )


# Specific exception classes for common scenarios
class ValidationError(ApplicationError):
    """Exception for validation errors."""

    def __init__(
        self,
        message: str,
        field_errors: dict[str, list[str]] | None = None,
        details: dict[str, Any] | None = None,
        trace_id: str | None = None,
        request_id: str | None = None,
    ) -> None:
        details = details or {}
        if field_errors:
            details["field_errors"] = field_errors
            details["total_fields_with_errors"] = len(field_errors)

        super().__init__(
            error_code=ErrorCode.VALIDATION_ERROR,
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
            trace_id=trace_id,
            request_id=request_id,
        )


class ResourceNotFoundError(ApplicationError):
    """Exception for resource not found errors."""

    def __init__(
        self,
        resource_type: str,
        resource_id: Any,
        search_criteria: dict[str, Any] | None = None,
        trace_id: str | None = None,
        request_id: str | None = None,
    ) -> None:
        message = f"{resource_type} with identifier '{resource_id}' was not found"

        details = {
            "resource_type": resource_type,
            "resource_id": str(resource_id),
        }

        if search_criteria:
            details["search_criteria"] = search_criteria
            message += f" using criteria: {search_criteria}"

        super().__init__(
            error_code=ErrorCode.RESOURCE_NOT_FOUND,
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            details=details,
            trace_id=trace_id,
            request_id=request_id,
        )


class AuthenticationError(ApplicationError):
    """Exception for authentication errors."""

    def __init__(
        self,
        message: str = "authentication failed",
        auth_method: str | None = None,
        trace_id: str | None = None,
        request_id: str | None = None,
    ) -> None:
        details = {}
        if auth_method:
            details["authentication_method"] = auth_method

        super().__init__(
            error_code=ErrorCode.AUTHENTICATION_ERROR,
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details,
            trace_id=trace_id,
            request_id=request_id,
        )


class AuthorizationError(ApplicationError):
    """Exception for authorization errors."""

    def __init__(
        self,
        message: str = "insufficient permissions to access this resource",
        required_permissions: list[str] | None = None,
        client_permissions: list[str] | None = None,
        resource: str | None = None,
        trace_id: str | None = None,
        request_id: str | None = None,
    ) -> None:
        details = {}
        if required_permissions:
            details["required_permissions"] = required_permissions
        if client_permissions:
            details["client_permissions"] = client_permissions
        if resource:
            details["protected_resource"] = resource

        super().__init__(
            error_code=ErrorCode.AUTHORIZATION_ERROR,
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            details=details,
            trace_id=trace_id,
            request_id=request_id,
        )


class BusinessRuleError(ApplicationError):
    """Exception for business rule violations."""

    def __init__(
        self,
        message: str,
        rule_name: str | None = None,
        rule_details: dict[str, Any] | None = None,
        details: dict[str, Any] | None = None,
        trace_id: str | None = None,
        request_id: str | None = None,
    ) -> None:
        details = details or {}
        if rule_name:
            details["violated_rule"] = rule_name
        if rule_details:
            details["rule_details"] = rule_details

        super().__init__(
            error_code=ErrorCode.BUSINESS_RULE_VIOLATION,
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details,
            trace_id=trace_id,
            request_id=request_id,
        )


class ExternalServiceError(ApplicationError):
    """Exception for external service errors."""

    def __init__(
        self,
        service_name: str,
        message: str,
        service_endpoint: str | None = None,
        response_status: int | None = None,
        response_body: str | None = None,
        trace_id: str | None = None,
        request_id: str | None = None,
    ) -> None:
        details = {
            "service_name": service_name,
        }

        if service_endpoint:
            details["service_endpoint"] = service_endpoint
        if response_status:
            details["response_status_code"] = response_status
        if response_body:
            details["response_body"] = response_body[:1000]  # Limit response body size

        full_message = f"external service '{service_name}' error: {message}"

        super().__init__(
            error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            message=full_message,
            status_code=status.HTTP_502_BAD_GATEWAY,
            details=details,
            trace_id=trace_id,
            request_id=request_id,
        )


class DatabaseError(ApplicationError):
    """Exception for database-related errors."""

    def __init__(
        self,
        message: str,
        operation: str | None = None,
        table_name: str | None = None,
        constraint_name: str | None = None,
        trace_id: str | None = None,
        request_id: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        details = {}
        if operation:
            details["database_operation"] = operation
        if table_name:
            details["table_name"] = table_name
        if constraint_name:
            details["constraint_violated"] = constraint_name

        super().__init__(
            error_code=ErrorCode.DATABASE_ERROR,
            message=f"database error: {message}",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details,
            trace_id=trace_id,
            request_id=request_id,
            cause=cause,
        )


class ClientError(ApplicationError):
    """Exception for client-related errors."""

    def __init__(
        self,
        error_code: ErrorCode,
        message: str,
        client_id: str | None = None,
        details: dict[str, Any] | None = None,
        trace_id: str | None = None,
        request_id: str | None = None,
    ) -> None:
        details = details or {}
        if client_id:
            details["client_id"] = client_id

        super().__init__(
            error_code=error_code,
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details,
            trace_id=trace_id,
            request_id=request_id,
        )


class TokenError(ApplicationError):
    """Exception for token-related errors."""

    def __init__(
        self,
        error_code: ErrorCode,
        message: str,
        token_type: str | None = None,
        details: dict[str, Any] | None = None,
        trace_id: str | None = None,
        request_id: str | None = None,
    ) -> None:
        details = details or {}
        if token_type:
            details["token_type"] = token_type

        super().__init__(
            error_code=error_code,
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details,
            trace_id=trace_id,
            request_id=request_id,
        )


class TaskError(ApplicationError):
    """Exception for task-related errors."""

    def __init__(
        self,
        error_code: ErrorCode,
        message: str,
        task_name: str | None = None,
        task_id: str | None = None,
        details: dict[str, Any] | None = None,
        trace_id: str | None = None,
        request_id: str | None = None,
    ) -> None:
        details = details or {}
        if task_name:
            details["task_name"] = task_name
        if task_id:
            details["task_id"] = task_id

        super().__init__(
            error_code=error_code,
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details,
            trace_id=trace_id,
            request_id=request_id,
        )
