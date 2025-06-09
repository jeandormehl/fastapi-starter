import json
import time
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from app.common.errors.error_response import StandardErrorResponse
from app.common.errors.errors import ApplicationError, ErrorCode
from app.common.middlewares.error_middleware import ErrorMiddleware
from app.common.utils import TraceContextExtractor


class TestErrorMiddleware:
    """Comprehensive test suite for ErrorMiddleware with StandardErrorResponse."""

    @pytest.fixture
    def mock_app(self):
        """Create a mock ASGI application."""
        return Mock(spec=ASGIApp)

    @pytest.fixture
    def middleware(self, mock_app):
        """Create ErrorMiddleware instance for testing."""
        return ErrorMiddleware(mock_app)

    @pytest.fixture
    def mock_call_next(self):
        """Mock call_next function for middleware testing."""
        return AsyncMock()

    @pytest.fixture
    def mock_request(self):
        """Create a mock request for testing."""
        request = MagicMock(spec=Request)
        request.state = MagicMock()
        request.state.trace_id = "test-trace-123"
        request.state.request_id = "test-request-456"
        request.url.path = "/api/test"
        request.method = "GET"
        request.client.host = "192.168.1.100"
        request.headers = {"user-agent": "test-agent"}
        return request

    @pytest.fixture
    def sample_response(self):
        """Create a sample successful response for testing."""
        response = JSONResponse({"message": "success"}, status_code=200)
        response.headers["content-type"] = "application/json"
        return response

    @pytest.mark.asyncio
    async def test_dispatch_successful_request(
        self, middleware, mock_request, mock_call_next, sample_response
    ):
        """Test successful request handling without exceptions."""
        mock_call_next.return_value = sample_response

        result = await middleware.dispatch(mock_request, mock_call_next)

        assert result == sample_response
        mock_call_next.assert_called_once_with(mock_request)

    @pytest.mark.asyncio
    async def test_dispatch_with_application_error(
        self, middleware, mock_request, mock_call_next
    ):
        """Test handling of ApplicationError with StandardErrorResponse."""
        app_error = ApplicationError(
            error_code=ErrorCode.VALIDATION_ERROR,
            message="Custom validation failed",
            details={"field": "test_field"},
        )
        mock_call_next.side_effect = app_error

        with patch.object(middleware._logger, "bind") as mock_bind:
            mock_logger = Mock()
            mock_bind.return_value = mock_logger

            result = await middleware.dispatch(mock_request, mock_call_next)

            # Verify response structure
            assert isinstance(result, JSONResponse)
            assert result.status_code == 400

            # Parse response content
            response_content = json.loads(result.body.decode("utf-8"))

            # Verify StandardErrorResponse structure
            assert "error" in response_content
            assert "message" in response_content
            assert "code" in response_content
            assert "timestamp" in response_content
            assert "trace_id" in response_content
            assert "request_id" in response_content
            assert "severity" in response_content

            # Verify specific values
            assert response_content["message"] == "Custom validation failed"
            assert response_content["code"] == "ERR_1001"
            assert response_content["trace_id"] == "test-trace-123"
            assert response_content["request_id"] == "test-request-456"

            # Verify headers
            assert result.headers["X-Trace-ID"] == "test-trace-123"
            assert result.headers["X-Request-ID"] == "test-request-456"
            assert result.headers["X-Error-Code"] == "ERR_1001"

    @pytest.mark.asyncio
    async def test_dispatch_with_http_exception(
        self, middleware, mock_request, mock_call_next
    ):
        """Test handling of HTTPException with StandardErrorResponse."""
        http_error = HTTPException(status_code=404, detail="Resource not found")
        mock_call_next.side_effect = http_error

        with patch.object(middleware._logger, "bind") as mock_bind:
            mock_logger = Mock()
            mock_bind.return_value = mock_logger

            result = await middleware.dispatch(mock_request, mock_call_next)

            # Verify response structure
            assert isinstance(result, JSONResponse)
            assert result.status_code == 404

            # Parse response content
            response_content = json.loads(result.body.decode("utf-8"))

            # Verify StandardErrorResponse structure
            assert response_content["error"] == "resource not found"
            assert response_content["code"] == ErrorCode.RESOURCE_NOT_FOUND.value
            assert response_content["trace_id"] == "test-trace-123"

    @pytest.mark.asyncio
    async def test_dispatch_with_validation_error(
        self, middleware, mock_request, mock_call_next
    ):
        """Test handling of RequestValidationError with StandardErrorResponse."""
        validation_errors = [
            {
                "loc": ("body", "email"),
                "msg": "field required",
                "type": "value_error.missing",
                "input": None,
            }
        ]
        validation_error = RequestValidationError(validation_errors)
        mock_call_next.side_effect = validation_error

        with patch.object(middleware._logger, "bind") as mock_bind:
            mock_logger = Mock()
            mock_bind.return_value = mock_logger

            result = await middleware.dispatch(mock_request, mock_call_next)

            # Verify response structure
            assert isinstance(result, JSONResponse)
            assert result.status_code == 422

            # Parse response content
            response_content = json.loads(result.body.decode())

            # Verify StandardErrorResponse structure
            assert response_content["error"] == "validation error"
            assert response_content["code"] == ErrorCode.VALIDATION_ERROR.value
            assert "validation failed for 1 field(s)" in response_content["message"]
            assert "validation_errors" in response_content["details"]

    @pytest.mark.asyncio
    async def test_dispatch_with_general_exception(
        self, middleware, mock_request, mock_call_next
    ):
        """Test handling of general Python exceptions with StandardErrorResponse."""
        general_error = ValueError("Unexpected error occurred")
        mock_call_next.side_effect = general_error

        with patch.object(middleware._logger, "bind") as mock_bind:
            mock_logger = Mock()
            mock_bind.return_value = mock_logger

            result = await middleware.dispatch(mock_request, mock_call_next)

            # Verify response structure
            assert isinstance(result, JSONResponse)
            assert result.status_code == 500

            # Parse response content
            response_content = json.loads(result.body.decode())

            # Verify StandardErrorResponse structure
            assert response_content["error"] == "internal server error"
            assert response_content["code"] == ErrorCode.INTERNAL_SERVER_ERROR.value
            assert response_content["message"] == "an unexpected error occurred"
            assert response_content["severity"] == "critical"
            assert "exception_type" in response_content["details"]
            assert response_content["details"]["exception_type"] == "ValueError"

    @pytest.mark.asyncio
    async def test_error_context_creation(self, middleware, mock_request):
        """Test comprehensive error context creation for logging."""
        test_exception = ValueError("Test error message")
        mock_response = JSONResponse({"error": "test"}, status_code=500)
        duration = 1.234
        trace_id = "trace-123"
        request_id = "req-456"

        with patch("traceback.format_exc", return_value="Mock traceback"):
            context = middleware._create_error_context(
                mock_request,
                test_exception,
                mock_response,
                duration,
                trace_id,
                request_id,
            )

            # Verify all expected fields are present
            expected_fields = [
                "trace_id",
                "request_id",
                "status_code",
                "duration_ms",
                "exception_type",
                "exception_message",
                "exception_module",
                "request_path",
                "request_method",
                "client_ip",
                "event",
            ]

            for field in expected_fields:
                assert field in context

            # Verify specific values
            assert context["trace_id"] == trace_id
            assert context["request_id"] == request_id
            assert context["status_code"] == 500
            assert context["duration_ms"] == 1234.0
            assert context["exception_type"] == "ValueError"
            assert context["exception_message"] == "Test error message"

    @pytest.mark.asyncio
    async def test_status_code_determination(self, middleware):
        """Test status code determination for different exception types."""
        # Test ApplicationError
        app_error = ApplicationError(
            error_code=ErrorCode.VALIDATION_ERROR, message="Test error", status_code=400
        )
        assert middleware._determine_status_code(app_error) == 400

        # Test HTTPException
        http_error = HTTPException(status_code=404, detail="Not found")
        assert middleware._determine_status_code(http_error) == 404

        # Test ValidationError
        validation_error = RequestValidationError([])
        assert middleware._determine_status_code(validation_error) == 422

        # Test general exception
        general_error = ValueError("Test error")
        assert middleware._determine_status_code(general_error) == 500

    @pytest.mark.asyncio
    async def test_log_severity_determination(self, middleware):
        """Test log severity determination for different exception types."""
        # Test validation error (should be warning)
        validation_error = ApplicationError(
            error_code=ErrorCode.VALIDATION_ERROR, message="Test validation error"
        )
        assert middleware._determine_log_severity(validation_error) == "warning"

        # Test server error (should be error)
        server_error = ApplicationError(
            error_code=ErrorCode.INTERNAL_SERVER_ERROR, message="Test server error"
        )
        assert middleware._determine_log_severity(server_error) == "error"

        # Test HTTP client error (should be warning)
        http_client_error = HTTPException(status_code=400, detail="Bad request")
        assert middleware._determine_log_severity(http_client_error) == "warning"

        # Test HTTP server error (should be error)
        http_server_error = HTTPException(status_code=500, detail="Server error")
        assert middleware._determine_log_severity(http_server_error) == "error"

        # Test connection error (should be critical)
        connection_error = Exception("Connection timeout occurred")
        assert middleware._determine_log_severity(connection_error) == "critical"

    @pytest.mark.asyncio
    async def test_standardized_error_response_creation(self, middleware):
        """
        Test creation of standardized error responses for different exception types.
        """
        trace_id = "test-trace"
        request_id = "test-request"

        # Test ApplicationError
        app_error = ApplicationError(
            error_code=ErrorCode.AUTHENTICATION_ERROR,
            message="Authentication failed",
            details={"reason": "invalid_token"},
        )
        response = middleware._create_standardized_error_response(
            app_error, trace_id, request_id
        )
        assert isinstance(response, StandardErrorResponse)
        assert response.code == ErrorCode.AUTHENTICATION_ERROR.value
        assert response.message == "Authentication failed"
        assert response.trace_id == trace_id

        # Test HTTPException
        http_error = HTTPException(status_code=401, detail="Unauthorized access")
        response = middleware._create_standardized_error_response(
            http_error, trace_id, request_id
        )
        assert isinstance(response, StandardErrorResponse)
        assert response.code == ErrorCode.AUTHENTICATION_ERROR.value
        assert response.message == "Unauthorized access"

        # Test general exception
        general_error = RuntimeError("Unexpected runtime error")
        response = middleware._create_standardized_error_response(
            general_error, trace_id, request_id
        )
        assert isinstance(response, StandardErrorResponse)
        assert response.code == ErrorCode.INTERNAL_SERVER_ERROR.value
        assert response.message == "an unexpected error occurred"
        assert "RuntimeError" in response.details["exception_type"]

    @pytest.mark.asyncio
    async def test_trace_context_setting(self, middleware):
        """Test safe setting of trace context on exceptions."""
        app_error = ApplicationError(
            error_code=ErrorCode.VALIDATION_ERROR, message="Test error"
        )

        # Initially no trace context
        assert app_error.trace_id is None
        assert app_error.request_id is None

        # Set trace context
        middleware._set_exception_context(app_error, "req-123", "trace-456")

        # Verify context was set
        assert app_error.request_id == "req-123"
        assert app_error.trace_id == "trace-456"

    @pytest.mark.asyncio
    async def test_performance_timing_accuracy(
        self, middleware, mock_request, mock_call_next
    ):
        """Test accurate performance timing calculation."""
        start_time = time.time()
        mock_request.state.start_time = start_time

        test_exception = ValueError("Test error")
        mock_call_next.side_effect = test_exception

        # Mock time.time() to return a specific end time
        end_time = start_time + 2.5  # 2.5 seconds later

        with (
            patch("time.time", return_value=end_time),
            patch.object(middleware._logger, "bind") as mock_bind,
        ):
            mock_logger = Mock()
            mock_bind.return_value = mock_logger

            await middleware.dispatch(mock_request, mock_call_next)

            # Verify duration calculation
            bind_call_args = mock_bind.call_args
            assert bind_call_args[1]["duration_ms"] == 2500.0

    @pytest.mark.asyncio
    async def test_request_state_initialization(
        self, middleware, mock_request, mock_call_next, sample_response
    ):
        """Test request state initialization when start_time is not set."""
        # Remove start_time from request state
        delattr(mock_request.state, "start_time")
        mock_call_next.return_value = sample_response

        with patch("time.time", return_value=123456.789) as mock_time:
            await middleware.dispatch(mock_request, mock_call_next)

            # Verify start_time was set
            assert mock_request.state.start_time == 123456.789
            mock_time.assert_called()

    @pytest.mark.asyncio
    async def test_missing_trace_context_fallback(self, middleware, mock_call_next):
        """Test fallback behavior when trace context is missing."""
        # Create request without trace context
        request = MagicMock(spec=Request)
        request.state = MagicMock()
        # Don't set trace_id and request_id
        request.url.path = "/test"
        request.method = "GET"
        request.client.host = "127.0.0.1"
        request.headers = {}

        test_exception = ValueError("Test error")
        mock_call_next.side_effect = test_exception

        with (
            patch.object(TraceContextExtractor, "get_trace_id", return_value="unknown"),
            patch.object(
                TraceContextExtractor, "get_request_id", return_value="unknown"
            ),
            patch.object(middleware._logger, "bind") as mock_bind,
        ):
            mock_logger = Mock()
            mock_bind.return_value = mock_logger

            result = await middleware.dispatch(request, mock_call_next)

            # Verify response contains unknown values
            assert result.headers["X-Trace-ID"] == "unknown"
            assert result.headers["X-Request-ID"] == "unknown"

            # Verify logging context uses unknown values
            bind_call_args = mock_bind.call_args
            assert bind_call_args[1]["trace_id"] == "unknown"
            assert bind_call_args[1]["request_id"] == "unknown"
