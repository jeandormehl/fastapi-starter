from unittest.mock import Mock, patch

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.common.errors.errors import ApplicationError, ErrorCode, ErrorDetail
from app.common.errors.exception_handlers import (
    EXCEPTION_HANDLERS,
    app_exception_handler,
    create_error_response,
    http_exception_handler,
    python_exception_handler,
    validation_exception_handler,
)


class MockRequest:
    """Mock request object for testing."""

    # noinspection HttpUrlsUsage
    def __init__(self, method="GET", path="/test"):
        self.method = method
        self.url = Mock()
        self.url.path = path
        self.url.base_url = "http://test.com"
        self.headers = {}
        self.query_params = {}
        self.client = Mock()
        self.client.host = "127.0.0.1"
        self.state = Mock()
        self.state.trace_id = "test-trace-id"
        self.state.request_id = "test-request-id"


class TestCreateErrorResponse:
    """Enhanced tests for create_error_response function."""

    @patch("app.common.errors.exception_handlers.get_logger")
    @patch("kink.di")
    def test_create_error_response_basic(self, _mock_di, mock_get_logger):  # noqa: PT019
        """Test basic error response creation."""

        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        mock_bound_logger = Mock()
        mock_logger.bind.return_value = mock_bound_logger

        error_detail = ErrorDetail(
            code="TEST_ERROR",
            message="Test error message",
            trace_id="trace-123",
            request_id="req-456",
        )

        response = create_error_response(error_detail, 400)

        assert response.status_code == 400
        assert "X-Trace-ID" in response.headers
        assert "X-Request-ID" in response.headers
        assert "X-Error-Code" in response.headers
        assert response.headers["X-Error-Code"] == "TEST_ERROR"

        mock_logger.bind.assert_called_once()
        mock_bound_logger.error.assert_called_once_with("api error response generated")

    @patch("app.common.errors.exception_handlers.get_logger")
    @patch("kink.di")
    def test_create_error_response_with_request_context(
        self,
        _mock_di,  # noqa: PT019
        mock_get_logger,
    ):
        """Test error response creation with request context."""

        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        mock_bound_logger = Mock()
        mock_logger.bind.return_value = mock_bound_logger

        request = MockRequest()
        request.headers["user-agent"] = "TestAgent/1.0"

        error_detail = ErrorDetail(
            code="VALIDATION_ERROR",
            message="Validation failed",
            trace_id="trace-789",
            request_id="req-101112",
        )

        create_error_response(error_detail, 422, request)

        # Verify logging context includes request information
        call_args = mock_logger.bind.call_args[1]
        assert call_args["request_method"] == "GET"
        assert call_args["request_path"] == "/test"
        assert call_args["client_ip"] == "127.0.0.1"
        assert call_args["user_agent"] == "TestAgent/1.0"

    @patch("app.common.errors.exception_handlers.get_logger")
    @patch("kink.di")
    def test_create_error_response_no_client_info(self, _mock_di, mock_get_logger):  # noqa: PT019
        """Test error response when request has no client information."""

        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        mock_bound_logger = Mock()
        mock_logger.bind.return_value = mock_bound_logger

        request = MockRequest()
        request.client = None

        error_detail = ErrorDetail(
            code="SERVER_ERROR",
            message="Server error",
            trace_id="trace-abc",
            request_id="req-def",
        )

        create_error_response(error_detail, 500, request)

        call_args = mock_logger.bind.call_args[1]
        assert call_args["client_ip"] == "unknown"
        assert call_args["user_agent"] == "unknown"


class TestAppExceptionHandler:
    """Tests for ApplicationError exception handler."""

    @patch("app.common.errors.exception_handlers.create_error_response")
    @patch("app.common.errors.exception_handlers.get_logger")
    async def test_app_exception_handler(self, mock_get_logger, mock_create_response):
        """Test application exception handling."""

        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        mock_bound_logger = Mock()
        mock_logger.bind.return_value = mock_bound_logger

        mock_response = Mock()
        mock_create_response.return_value = mock_response

        app_error = ApplicationError(
            error_code=ErrorCode.VALIDATION_ERROR,
            message="Custom validation error",
            status_code=400,
        )

        request = MockRequest()
        result = await app_exception_handler(request, app_error)

        assert result == mock_response
        mock_bound_logger.warning.assert_called_once()
        mock_create_response.assert_called_once()


class TestHttpExceptionHandler:
    """Tests for HTTP exception handler."""

    @patch("app.common.errors.exception_handlers.create_error_response")
    @patch("kink.di")
    async def test_http_exception_handler_404(self, mock_di, mock_create_response):
        """Test 404 HTTP exception handling."""

        mock_di.__getitem__.return_value = Mock()  # timezone mock
        mock_response = Mock()
        mock_create_response.return_value = mock_response

        http_exc = HTTPException(status_code=404, detail="Not found")
        request = MockRequest(path="/api/users/999")

        result = await http_exception_handler(request, http_exc)

        assert result == mock_response

        # Verify error detail creation
        call_args = mock_create_response.call_args[0]
        error_detail = call_args[0]
        assert (
            "the requested resource '/api/users/999' was not found"
            in error_detail.message
        )

    @patch("app.common.errors.exception_handlers.create_error_response")
    @patch("kink.di")
    async def test_http_exception_handler_401(self, mock_di, mock_create_response):
        """Test 401 HTTP exception handling."""

        mock_di.__getitem__.return_value = Mock()
        mock_response = Mock()
        mock_create_response.return_value = mock_response

        http_exc = HTTPException(status_code=401, detail="Unauthorized")
        request = MockRequest()

        await http_exception_handler(request, http_exc)

        call_args = mock_create_response.call_args[0]
        error_detail = call_args[0]
        assert "authentication is required" in error_detail.message

    @patch("app.common.errors.exception_handlers.create_error_response")
    @patch("kink.di")
    async def test_http_exception_handler_unknown_status(
        self, mock_di, mock_create_response
    ):
        """Test HTTP exception with unknown status code."""

        mock_di.__getitem__.return_value = Mock()
        mock_response = Mock()
        mock_create_response.return_value = mock_response

        http_exc = HTTPException(status_code=418, detail="I'm a teapot")
        request = MockRequest()

        await http_exception_handler(request, http_exc)

        call_args = mock_create_response.call_args[0]
        error_detail = call_args[0]
        assert error_detail.code == ErrorCode.INTERNAL_SERVER_ERROR.value


class TestValidationExceptionHandler:
    """Tests for request validation exception handler."""

    @patch("app.common.errors.exception_handlers.create_error_response")
    @patch("kink.di")
    async def test_validation_exception_handler(self, mock_di, mock_create_response):
        """Test validation exception handling with multiple errors."""

        mock_di.__getitem__.return_value = Mock()
        mock_response = Mock()
        mock_create_response.return_value = mock_response

        # Mock validation errors
        validation_errors = [
            {
                "loc": ("body", "email"),
                "msg": "field required",
                "type": "value_error.missing",
                "input": None,
            },
            {
                "loc": ("body", "age"),
                "msg": "ensure this value is greater than 0",
                "type": "value_error.number.not_gt",
                "input": -5,
            },
        ]

        validation_exc = RequestValidationError(validation_errors)
        request = MockRequest()
        request.headers["content-type"] = "application/json"

        result = await validation_exception_handler(request, validation_exc)

        assert result == mock_response

        # Verify error detail structure
        call_args = mock_create_response.call_args[0]
        error_detail = call_args[0]
        assert error_detail.code == ErrorCode.VALIDATION_ERROR.value
        assert "validation failed for 2 field(s)" in error_detail.message
        assert "validation_errors" in error_detail.details
        assert "field_errors" in error_detail.details

    @patch("app.common.errors.exception_handlers.create_error_response")
    @patch("kink.di")
    async def test_validation_exception_handler_empty_errors(
        self, mock_di, mock_create_response
    ):
        """Test validation exception handler with empty error list."""

        mock_di.__getitem__.return_value = Mock()
        mock_response = Mock()
        mock_create_response.return_value = mock_response

        validation_exc = RequestValidationError([])
        request = MockRequest()

        await validation_exception_handler(request, validation_exc)

        call_args = mock_create_response.call_args[0]
        error_detail = call_args[0]
        assert "validation failed for 0 field(s)" in error_detail.message


class TestPythonExceptionHandler:
    """Tests for general Python exception handler."""

    @patch("app.common.errors.exception_handlers.create_error_response")
    @patch("app.common.errors.exception_handlers.get_logger")
    @patch("kink.di")
    async def test_python_exception_handler(
        self, mock_di, mock_get_logger, mock_create_response
    ):
        """Test general Python exception handling."""

        mock_di.__getitem__.return_value = Mock()
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        mock_bound_logger = Mock()
        mock_logger.bind.return_value = mock_bound_logger
        mock_response = Mock()
        mock_create_response.return_value = mock_response

        test_exception = ValueError("Test runtime error")
        request = MockRequest()

        result = await python_exception_handler(request, test_exception)

        assert result == mock_response
        mock_bound_logger.critical.assert_called_once_with(
            "unhandled exception occurred"
        )

        # Verify logging context
        call_args = mock_logger.bind.call_args[1]
        assert call_args["exception_type"] == "ValueError"
        assert call_args["exception_message"] == "Test runtime error"
        assert "traceback" in call_args

    @patch("app.common.errors.exception_handlers.create_error_response")
    @patch("app.common.errors.exception_handlers.get_logger")
    @patch("kink.di")
    async def test_python_exception_handler_sanitized_response(
        self, mock_di, mock_get_logger, mock_create_response
    ):
        """Test that sensitive information is not exposed in response."""

        mock_di.__getitem__.return_value = Mock()
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        mock_bound_logger = Mock()
        mock_logger.bind.return_value = mock_bound_logger
        mock_response = Mock()
        mock_create_response.return_value = mock_response

        # Exception with sensitive information
        sensitive_exception = Exception("Database password: secret123")
        request = MockRequest()

        await python_exception_handler(request, sensitive_exception)

        # Verify response doesn't contain sensitive info
        call_args = mock_create_response.call_args[0]
        error_detail = call_args[0]
        assert "secret123" not in error_detail.message
        assert "an unexpected error occurred" in error_detail.message


class TestExceptionHandlersRegistry:
    """Tests for exception handlers registry."""

    def test_exception_handlers_registry_completeness(self):
        """Test that all expected exception types are registered."""

        expected_types = [
            ApplicationError,
            HTTPException,
            StarletteHTTPException,
            RequestValidationError,
            ValidationError,
            Exception,
        ]

        for exc_type in expected_types:
            assert exc_type in EXCEPTION_HANDLERS
            assert callable(EXCEPTION_HANDLERS[exc_type])

    def test_exception_handlers_hierarchy(self):
        """Test that exception handler hierarchy is correct."""

        # More specific exceptions should be handled before general ones
        assert ApplicationError in EXCEPTION_HANDLERS
        assert Exception in EXCEPTION_HANDLERS

        # Verify that the general Exception handler is the most generic
        assert EXCEPTION_HANDLERS[Exception] == python_exception_handler
