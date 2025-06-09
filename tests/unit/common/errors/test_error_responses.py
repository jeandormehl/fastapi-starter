from fastapi import status

from app.common.errors.error_response import (
    ErrorResponseBuilder,
    ErrorSeverity,
    StandardErrorResponse,
    create_error_response_json,
)
from app.common.errors.errors import ErrorCode


class TestStandardErrorResponse:
    """Test cases for StandardErrorResponse."""

    def test_create_basic_error_response(self):
        """Test creating a basic error response."""

        response = StandardErrorResponse.create(
            error="Test Error", message="Test message", code="test_error"
        )

        assert response.error == "Test Error"
        assert response.message == "Test message"
        assert response.code == "test_error"
        assert response.severity == ErrorSeverity.MEDIUM
        assert response.details == {}
        assert isinstance(response.timestamp, str)

    def test_create_detailed_error_response(self):
        """Test creating a detailed error response."""

        details = {"field": "value", "count": 42}
        response = StandardErrorResponse.create(
            error="Validation Error",
            message="Invalid input",
            code=ErrorCode.VALIDATION_ERROR,
            details=details,
            trace_id="test-trace-123",
            request_id="test-request-456",
            severity=ErrorSeverity.LOW,
        )

        assert response.error == "Validation Error"
        assert response.message == "Invalid input"
        assert response.code == ErrorCode.VALIDATION_ERROR.value
        assert response.details == details
        assert response.trace_id == "test-trace-123"
        assert response.request_id == "test-request-456"
        assert response.severity == ErrorSeverity.LOW


class TestErrorResponseBuilder:
    """Test cases for ErrorResponseBuilder."""

    def test_validation_error(self):
        """Test validation error creation."""

        response = ErrorResponseBuilder.validation_error(
            message="Invalid email format",
            details={"field": "email"},
            trace_id="trace-123",
        )

        assert response.error == "validation error"
        assert response.message == "Invalid email format"
        assert response.code == ErrorCode.VALIDATION_ERROR.value
        assert response.details == {"field": "email"}
        assert response.trace_id == "trace-123"
        assert response.severity == ErrorSeverity.LOW

    def test_authentication_error(self):
        """Test authentication error creation."""

        response = ErrorResponseBuilder.authentication_error(
            trace_id="trace-123", request_id="request-456"
        )

        assert response.error == "authentication error"
        assert response.message == "authentication required"
        assert response.code == ErrorCode.AUTHENTICATION_ERROR.value
        assert response.trace_id == "trace-123"
        assert response.request_id == "request-456"
        assert response.severity == ErrorSeverity.MEDIUM

    def test_not_found_error(self):
        """Test not found error creation."""

        response = ErrorResponseBuilder.not_found_error(
            resource="User", trace_id="trace-123"
        )

        assert response.error == "resource not found"
        assert response.message == "User not found"
        assert response.code == ErrorCode.RESOURCE_NOT_FOUND.value
        assert response.trace_id == "trace-123"
        assert response.severity == ErrorSeverity.LOW

    def test_internal_server_error(self):
        """Test internal server error creation."""

        details = {"exception": "DatabaseError"}
        response = ErrorResponseBuilder.internal_server_error(
            message="database connection failed", details=details, trace_id="trace-123"
        )

        assert response.error == "internal server error"
        assert response.message == "database connection failed"
        assert response.code == ErrorCode.INTERNAL_SERVER_ERROR.value
        assert response.details == details
        assert response.trace_id == "trace-123"
        assert response.severity == ErrorSeverity.CRITICAL

    def test_rate_limit_error(self):
        """Test rate limit error creation."""
        response = ErrorResponseBuilder.rate_limit_error(
            message="Too many requests", retry_after=60, trace_id="trace-123"
        )

        assert response.error == "rate limit exceeded"
        assert response.message == "Too many requests"
        assert response.code == ErrorCode.RATE_LIMIT_EXCEEDED.value
        assert response.details == {"retry_after_seconds": 60}
        assert response.trace_id == "trace-123"
        assert response.severity == ErrorSeverity.MEDIUM


class TestCreateErrorResponseJson:
    """Test cases for create_error_response_json function."""

    def test_create_json_response(self):
        """Test creating JSON response from StandardErrorResponse."""
        error_response = ErrorResponseBuilder.validation_error(
            message="Invalid input", trace_id="trace-123", request_id="request-456"
        )

        json_response = create_error_response_json(
            error_response, status.HTTP_400_BAD_REQUEST
        )

        assert json_response["status_code"] == status.HTTP_400_BAD_REQUEST

        resp = json_response["content"]

        assert resp["error"] == "validation error"
        assert resp["message"] == "Invalid input"
        assert resp["code"] == ErrorCode.VALIDATION_ERROR.value

        assert json_response["headers"]["X-Trace-ID"] == "trace-123"
        assert json_response["headers"]["X-Request-ID"] == "request-456"
        assert (
            json_response["headers"]["X-Error-Code"] == ErrorCode.VALIDATION_ERROR.value
        )

    def test_create_json_response_unknown_ids(self):
        """Test creating JSON response with unknown trace/request IDs."""
        error_response = ErrorResponseBuilder.internal_server_error()

        json_response = create_error_response_json(error_response)

        assert json_response["headers"]["X-Trace-ID"] == "unknown"
        assert json_response["headers"]["X-Request-ID"] == "unknown"
