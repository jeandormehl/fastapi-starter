from fastapi import status

from app.core.errors.errors import (
    AppError,
    AuthenticationError,
    AuthorizationError,
    BusinessRuleError,
    DatabaseError,
    ErrorCode,
    ErrorDetail,
    ExternalServiceError,
    ResourceConflictError,
    ResourceNotFoundError,
    ValidationError,
)


class TestErrorCode:
    """Test error code enumeration."""

    def test_error_code_values(self):
        """Test error code string values."""
        assert ErrorCode.INTERNAL_SERVER_ERROR.value == "ERR_1000"
        assert ErrorCode.VALIDATION_ERROR.value == "ERR_1001"
        assert ErrorCode.AUTHENTICATION_ERROR.value == "ERR_1002"
        assert ErrorCode.RESOURCE_NOT_FOUND.value == "ERR_2000"
        assert ErrorCode.BUSINESS_RULE_VIOLATION.value == "ERR_3000"
        assert ErrorCode.EXTERNAL_SERVICE_ERROR.value == "ERR_4000"
        assert ErrorCode.DATA_CORRUPTION.value == "ERR_5000"


class TestErrorDetail:
    """Test error detail model."""

    def test_error_detail_creation(self):
        """Test error detail model creation."""

        detail = ErrorDetail(
            code="ERR_1000",
            message="Test error",
            trace_id="test-trace",
            request_id="test-request",
        )

        assert detail.code == "ERR_1000"
        assert detail.message == "Test error"
        assert detail.trace_id == "test-trace"
        assert detail.request_id == "test-request"
        assert detail.details == {}

    def test_error_detail_with_details(self):
        """Test error detail with additional details."""

        detail = ErrorDetail(
            code="ERR_1001",
            message="Validation failed",
            details={"field": "username", "reason": "required"},
        )

        assert detail.details["field"] == "username"
        assert detail.details["reason"] == "required"


class TestAppException:
    """Test base application exception."""

    def test_app_exception_creation(self):
        """Test basic exception creation."""

        exc = AppError(
            error_code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="Test error",
            trace_id="test-trace",
            request_id="test-request",
        )

        assert exc.error_code == ErrorCode.INTERNAL_SERVER_ERROR
        assert exc.message == "Test error"
        assert exc.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc.trace_id == "test-trace"
        assert exc.request_id == "test-request"
        assert str(exc) == "Test error"

    def test_app_exception_with_cause(self):
        """Test exception with underlying cause."""

        cause = ValueError("Original error")
        exc = AppError(
            error_code=ErrorCode.VALIDATION_ERROR,
            message="Validation failed",
            cause=cause,
        )

        assert exc.cause == cause
        assert exc.details["caused_by"] == "ValueError"
        assert exc.details["cause_message"] == "Original error"

    def test_to_error_detail(self):
        """Test conversion to error detail."""

        exc = AppError(
            error_code=ErrorCode.AUTHENTICATION_ERROR,
            message="Auth failed",
            trace_id="trace-123",
            request_id="req-123",
            details={"method": "jwt"},
        )

        detail = exc.to_error_detail()

        assert detail.code == "ERR_1002"
        assert detail.message == "Auth failed"
        assert detail.trace_id == "trace-123"
        assert detail.request_id == "req-123"
        assert detail.details["method"] == "jwt"
        assert detail.timestamp is not None


class TestValidationException:
    """Test validation exception."""

    def test_validation_exception_basic(self):
        """Test basic validation exception."""

        exc = ValidationError(message="Validation failed", trace_id="trace-123")

        assert exc.error_code == ErrorCode.VALIDATION_ERROR
        assert exc.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert exc.message == "Validation failed"

    def test_validation_exception_with_field_errors(self):
        """Test validation exception with field errors."""

        field_errors = {
            "username": ["This field is required"],
            "email": ["Invalid email format", "Email already exists"],
        }

        exc = ValidationError(
            message="Multiple validation errors", field_errors=field_errors
        )

        assert exc.details["field_errors"] == field_errors
        assert exc.details["total_fields_with_errors"] == 2


class TestResourceNotFoundException:
    """Test resource not found exception."""

    def test_resource_not_found_basic(self):
        """Test basic resource not found."""

        exc = ResourceNotFoundError(resource_type="User", resource_id="123")

        assert exc.error_code == ErrorCode.RESOURCE_NOT_FOUND
        assert exc.status_code == status.HTTP_404_NOT_FOUND
        assert "User with identifier '123' was not found" in exc.message
        assert exc.details["resource_type"] == "User"
        assert exc.details["resource_id"] == "123"

    def test_resource_not_found_with_criteria(self):
        """Test resource not found with search criteria."""

        search_criteria = {"email": "test@example.com", "active": True}
        exc = ResourceNotFoundError(
            resource_type="User",
            resource_id="test@example.com",
            search_criteria=search_criteria,
        )

        assert exc.details["search_criteria"] == search_criteria
        assert "using criteria:" in exc.message


class TestResourceConflictException:
    """Test resource conflict exception."""

    def test_resource_conflict_basic(self):
        """Test basic resource conflict."""

        exc = ResourceConflictError(
            resource_type="User",
            resource_id="testuser",
            conflict_reason="username already taken",
        )

        assert exc.error_code == ErrorCode.RESOURCE_ALREADY_EXISTS
        assert exc.status_code == status.HTTP_409_CONFLICT
        assert "User 'testuser' already exists: username already taken" in exc.message
        assert exc.details["conflict_reason"] == "username already taken"

    def test_resource_conflict_with_existing_info(self):
        """Test resource conflict with existing resource info."""

        existing_info = {"id": "456", "created_at": "2023-01-01"}
        exc = ResourceConflictError(
            resource_type="User",
            resource_id="testuser",
            conflict_reason="duplicate email",
            existing_resource_info=existing_info,
        )

        assert exc.details["existing_resource"] == existing_info


class TestAuthenticationException:
    """Test authentication exception."""

    def test_authentication_exception_basic(self):
        """Test basic authentication exception."""

        exc = AuthenticationError()

        assert exc.error_code == ErrorCode.AUTHENTICATION_ERROR
        assert exc.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc.message == "authentication failed"

    def test_authentication_exception_with_method(self):
        """Test authentication exception with method."""

        exc = AuthenticationError(message="JWT token invalid", auth_method="jwt")

        assert exc.message == "JWT token invalid"
        assert exc.details["authentication_method"] == "jwt"


class TestAuthorizationException:
    """Test authorization exception."""

    def test_authorization_exception_basic(self):
        """Test basic authorization exception."""

        exc = AuthorizationError()

        assert exc.error_code == ErrorCode.AUTHORIZATION_ERROR
        assert exc.status_code == status.HTTP_403_FORBIDDEN
        assert "insufficient permissions" in exc.message

    def test_authorization_exception_with_permissions(self):
        """Test authorization exception with permission details."""

        exc = AuthorizationError(
            message="Access denied",
            required_permissions=["read", "write"],
            client_permissions=["read"],
            resource="/api/users",
        )

        assert exc.details["required_permissions"] == ["read", "write"]
        assert exc.details["client_permissions"] == ["read"]
        assert exc.details["protected_resource"] == "/api/users"


class TestBusinessRuleException:
    """Test business rule exception."""

    def test_business_rule_exception_basic(self):
        """Test basic business rule exception."""

        exc = BusinessRuleError(message="Business rule violated")

        assert exc.error_code == ErrorCode.BUSINESS_RULE_VIOLATION
        assert exc.status_code == status.HTTP_400_BAD_REQUEST

    def test_business_rule_exception_with_rule_details(self):
        """Test business rule exception with rule details."""

        rule_details = {"min_age": 18, "provided_age": 16}
        exc = BusinessRuleError(
            message="Age requirement not met",
            rule_name="minimum_age_check",
            rule_details=rule_details,
        )

        assert exc.details["violated_rule"] == "minimum_age_check"
        assert exc.details["rule_details"] == rule_details


class TestExternalServiceException:
    """Test external service exception."""

    def test_external_service_exception_basic(self):
        """Test basic external service exception."""

        exc = ExternalServiceError(
            service_name="PaymentAPI", message="Service unavailable"
        )

        assert exc.error_code == ErrorCode.EXTERNAL_SERVICE_ERROR
        assert exc.status_code == status.HTTP_502_BAD_GATEWAY
        assert "external service 'PaymentAPI' error: Service unavailable" in exc.message
        assert exc.details["service_name"] == "PaymentAPI"

    def test_external_service_exception_with_response_details(self):
        """Test external service exception with response details."""

        exc = ExternalServiceError(
            service_name="PaymentAPI",
            message="Bad request",
            service_endpoint="https://api.payment.com/charge",
            response_status=400,
            response_body='{"error": "Invalid card"}',
        )

        assert exc.details["service_endpoint"] == "https://api.payment.com/charge"
        assert exc.details["response_status_code"] == 400
        assert exc.details["response_body"] == '{"error": "Invalid card"}'


class TestDatabaseException:
    """Test database exception."""

    def test_database_exception_basic(self):
        """Test basic database exception."""

        exc = DatabaseError(message="Connection failed")

        assert exc.error_code == ErrorCode.DATABASE_CONNECTION
        assert exc.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "database error: Connection failed" in exc.message

    def test_database_exception_with_operation_details(self):
        """Test database exception with operation details."""

        cause = Exception("Connection timeout")
        exc = DatabaseError(
            message="Query failed",
            operation="SELECT",
            table_name="users",
            constraint_name="unique_email",
            cause=cause,
        )

        assert exc.details["database_operation"] == "SELECT"
        assert exc.details["table_name"] == "users"
        assert exc.details["constraint_violated"] == "unique_email"
        assert exc.cause == cause
