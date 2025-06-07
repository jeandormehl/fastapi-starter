import time
from unittest.mock import AsyncMock, Mock, patch

import pytest
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from app.common.middlewares.error_middleware import ErrorMiddleware
from app.core.errors.errors import ApplicationError, ErrorCode
from app.core.errors.exception_handlers import EXCEPTION_HANDLERS


class TestErrorMiddleware:
    """Comprehensive test suite for ErrorMiddleware."""

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
    def sample_response(self):
        """Create a sample response for testing."""

        response = JSONResponse({"message": "success"}, status_code=200)
        response.headers["content-type"] = "application/json"
        return response

    @pytest.fixture
    def error_response(self):
        """Create an error response for testing."""

        response = JSONResponse(
            {"error": "Internal Server Error", "code": "INTERNAL_ERROR"},
            status_code=500,
        )
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
    async def test_dispatch_with_exception(
        self, middleware, mock_request, mock_call_next
    ):
        """Test exception handling during request processing."""

        test_exception = ValueError("Test error")
        mock_call_next.side_effect = test_exception

        # Mock the _handle_exception method
        mock_response = JSONResponse({"error": "handled"}, status_code=500)
        with patch.object(
            middleware, "_handle_exception", return_value=mock_response
        ) as mock_handle:
            result = await middleware.dispatch(mock_request, mock_call_next)

            assert result == mock_response
            mock_handle.assert_called_once_with(mock_request, test_exception)

    @pytest.mark.asyncio
    async def test_handle_exception_with_trace_context(
        self, middleware, mock_request, error_response
    ):
        """Test exception handling with proper trace context."""

        # Setup request state
        mock_request.state.start_time = time.time() - 0.5
        mock_request.state.trace_id = "test-trace-123"
        mock_request.state.request_id = "test-request-456"

        test_exception = ValueError("Test error message")

        with (
            patch.object(
                middleware,
                "_find_exception_handler",
                return_value=AsyncMock(return_value=error_response),
            ) as mock_find_handler,
            patch.object(middleware._logger, "bind") as mock_bind,
        ):
            mock_logger = Mock()
            mock_bind.return_value = mock_logger

            result = await middleware._handle_exception(mock_request, test_exception)

            # Verify handler was found and called
            mock_find_handler.assert_called_once_with(test_exception)

            # Verify logging was called with proper context
            mock_bind.assert_called_once()
            bind_call_args = mock_bind.call_args[1]

            assert bind_call_args["trace_id"] == "test-trace-123"
            assert bind_call_args["request_id"] == "test-request-456"
            assert bind_call_args["exception_type"] == "ValueError"
            assert bind_call_args["exception_message"] == "Test error message"
            assert "duration_ms" in bind_call_args

            mock_logger.error.assert_called_once_with("request failed with exception")

            # Verify trace headers were added
            assert result.headers["X-Trace-ID"] == "test-trace-123"
            assert result.headers["X-Request-ID"] == "test-request-456"

    @pytest.mark.asyncio
    async def test_handle_exception_with_app_exception(
        self, middleware, mock_request, error_response
    ):
        """Test handling of AppException with proper context assignment."""

        mock_request.state.trace_id = "test-trace-123"
        mock_request.state.request_id = "test-request-456"
        mock_request.state.start_time = time.time()

        app_exception = ApplicationError(
            error_code=ErrorCode.VALIDATION_ERROR,
            message="Validation failed",
            details={"field": "value"},
        )

        with (
            patch.object(
                middleware,
                "_find_exception_handler",
                return_value=AsyncMock(return_value=error_response),
            ),
            patch.object(middleware._logger, "bind") as mock_bind,
        ):
            mock_logger = Mock()
            mock_bind.return_value = mock_logger

            await middleware._handle_exception(mock_request, app_exception)

            # Verify trace information was set on exception
            assert app_exception.trace_id == "test-trace-123"
            assert app_exception.request_id == "test-request-456"

    @pytest.mark.asyncio
    async def test_handle_exception_without_trace_context(
        self, middleware, mock_request, error_response
    ):
        """Test exception handling when trace context is missing."""

        # Remove trace context
        del mock_request.state.trace_id
        del mock_request.state.request_id
        mock_request.state.start_time = time.time()

        test_exception = ValueError("Test error")

        with (
            patch.object(
                middleware,
                "_find_exception_handler",
                return_value=AsyncMock(return_value=error_response),
            ),
            patch.object(middleware._logger, "bind") as mock_bind,
        ):
            mock_logger = Mock()
            mock_bind.return_value = mock_logger

            result = await middleware._handle_exception(mock_request, test_exception)

            # Verify unknown values were used
            bind_call_args = mock_bind.call_args[1]
            assert bind_call_args["trace_id"] == "unknown"
            assert bind_call_args["request_id"] == "unknown"

            # Verify headers still added with unknown values
            assert result.headers["X-Trace-ID"] == "unknown"
            assert result.headers["X-Request-ID"] == "unknown"

    def test_find_exception_handler_specific_type(self, middleware):
        """Test finding specific exception handler."""

        # Create a test exception that should have a specific handler
        validation_error = ApplicationError(
            error_code=ErrorCode.VALIDATION_ERROR, message="Test validation error"
        )

        handler = middleware._find_exception_handler(validation_error)

        # Verify correct handler is returned (AppException should have specific handler)
        assert handler is not None
        assert handler in EXCEPTION_HANDLERS.values()

    def test_find_exception_handler_fallback(self, middleware):
        """Test fallback to generic Exception handler."""

        # Create an exception type that doesn't have a specific handler
        custom_exception = RuntimeError("Custom error")

        handler = middleware._find_exception_handler(custom_exception)

        # Should fall back to Exception handler
        assert handler == EXCEPTION_HANDLERS[Exception]

    def test_create_error_context_comprehensive(self, middleware, mock_request):
        """Test comprehensive error context creation."""

        # Setup comprehensive request mock
        mock_request.url.path = "/api/test"
        mock_request.method = "POST"
        mock_request.client.host = "192.168.1.100"

        test_exception = ValueError("Test error message")

        mock_response = JSONResponse({"error": "test"}, status_code=400)
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
            assert context["status_code"] == 400
            assert context["duration_ms"] == 1234.0
            assert context["exception_type"] == "ValueError"
            assert context["exception_message"] == "Test error message"
            assert context["request_path"] == "/api/test"
            assert context["request_method"] == "POST"
            assert context["client_ip"] == "192.168.1.100"
            assert context["event"] == "request_failed"

    def test_create_error_context_without_traceback(self, middleware, mock_request):
        """Test error context creation when exception has no traceback."""

        test_exception = ValueError("Test error")
        test_exception.__traceback__ = None

        mock_response = JSONResponse({"error": "test"}, status_code=500)

        context = middleware._create_error_context(
            mock_request, test_exception, mock_response, 0.5, "trace", "request"
        )

        # Verify traceback is not included when not available
        assert "traceback" not in context

    def test_create_error_context_no_client(self, middleware, mock_request):
        """Test error context creation when request has no client."""

        mock_request.client = None
        test_exception = ValueError("Test error")
        mock_response = JSONResponse({"error": "test"}, status_code=500)

        context = middleware._create_error_context(
            mock_request, test_exception, mock_response, 0.5, "trace", "request"
        )

        assert context["client_ip"] == "unknown"

    @pytest.mark.asyncio
    async def test_multiple_exception_types(self, middleware, mock_request):
        """Test handling of various exception types."""

        mock_request.state.start_time = time.time()
        mock_request.state.trace_id = "trace-123"
        mock_request.state.request_id = "req-456"

        exception_types = [
            ValueError("Value error"),
            KeyError("Key error"),
            TypeError("Type error"),
            RuntimeError("Runtime error"),
            ApplicationError(ErrorCode.INTERNAL_SERVER_ERROR, "App error"),
        ]

        for exception in exception_types:
            mock_response = JSONResponse({"error": "handled"}, status_code=500)

            with (
                patch.object(
                    middleware,
                    "_find_exception_handler",
                    return_value=AsyncMock(return_value=mock_response),
                ),
                patch.object(middleware._logger, "bind") as mock_bind,
            ):
                mock_logger = Mock()
                mock_bind.return_value = mock_logger

                result = await middleware._handle_exception(mock_request, exception)

                # Verify each exception type is handled properly
                assert result.status_code == 500
                mock_logger.error.assert_called_once()

                # Reset mock for next iteration
                mock_bind.reset_mock()

    @pytest.mark.asyncio
    async def test_performance_timing_accuracy(self, middleware, mock_request):
        """Test accurate performance timing calculation."""

        start_time = time.time()
        mock_request.state.start_time = start_time
        mock_request.state.trace_id = "trace-123"
        mock_request.state.request_id = "req-456"

        test_exception = ValueError("Test error")
        mock_response = JSONResponse({"error": "handled"}, status_code=500)

        # Mock time.time() to return a specific end time
        end_time = start_time + 2.5  # 2.5 seconds later

        with (
            patch("time.time", return_value=end_time),
            patch.object(
                middleware,
                "_find_exception_handler",
                return_value=AsyncMock(return_value=mock_response),
            ),
            patch.object(middleware._logger, "bind") as mock_bind,
        ):
            mock_logger = Mock()
            mock_bind.return_value = mock_logger

            await middleware._handle_exception(mock_request, test_exception)

            # Verify duration calculation
            bind_call_args = mock_bind.call_args[1]
            assert bind_call_args["duration_ms"] == 2500.0

    @pytest.mark.asyncio
    async def test_logging_context_binding(self, middleware, mock_request):
        """Test proper context binding for structured logging."""

        mock_request.state.start_time = time.time()
        mock_request.state.trace_id = "trace-123"
        mock_request.state.request_id = "req-456"
        mock_request.url.path = "/test/endpoint"
        mock_request.method = "GET"

        test_exception = ValueError("Detailed test error")
        mock_response = JSONResponse({"error": "handled"}, status_code=400)

        with (
            patch.object(
                middleware,
                "_find_exception_handler",
                return_value=AsyncMock(return_value=mock_response),
            ),
            patch.object(middleware._logger, "bind") as mock_bind,
        ):
            mock_logger = Mock()
            mock_bind.return_value = mock_logger

            await middleware._handle_exception(mock_request, test_exception)

            # Verify the logger was bound with comprehensive context
            mock_bind.assert_called_once()
            context = mock_bind.call_args[1]

            # Verify context structure for observability
            required_observability_fields = [
                "trace_id",
                "request_id",
                "status_code",
                "duration_ms",
                "exception_type",
                "exception_message",
                "request_path",
                "request_method",
                "client_ip",
                "event",
            ]

            for field in required_observability_fields:
                assert field in context, f"Missing observability field: {field}"

            # Verify structured logging call
            mock_logger.error.assert_called_once_with("request failed with exception")
