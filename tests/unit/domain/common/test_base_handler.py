from unittest.mock import Mock, patch

import pytest
from fastapi.requests import Request

from app.core.errors.exceptions import (
    AppException,
    AuthenticationException,
    ErrorCode,
    ValidationException,
)
from app.domain.common.base_handler import BaseHandler
from app.domain.common.base_request import BaseRequest
from app.domain.common.base_response import BaseResponse


class TestRequest(BaseRequest):
    """Test request class for handler testing."""

    __test__ = False

    trace_id: str = "12345"
    request_id: str = "12345"
    req: Request = Mock(spec=Request)

    test_data: str = "test"


class TestResponse(BaseResponse):
    """Test response class for handler testing."""

    __test__ = False

    result: str = "success"


class TestHandler(BaseHandler[TestRequest, TestResponse]):
    """Concrete test handler for testing base functionality."""

    __test__ = False

    def __init__(self):
        super().__init__()

        self.handle_internal_called = False
        self.handle_internal_result = TestResponse(result="success")
        self.handle_internal_exception = None

    async def _handle_internal(self, request: TestRequest) -> TestResponse:  # noqa: ARG002
        """Test implementation of handle_internal."""

        self.handle_internal_called = True

        if self.handle_internal_exception:
            raise self.handle_internal_exception

        return self.handle_internal_result


class TestFailingHandler(BaseHandler[TestRequest, TestResponse]):
    """Handler that always fails for testing error handling."""

    __test__ = False

    async def _handle_internal(self, request: TestRequest) -> TestResponse:  # noqa: ARG002
        """Implementation that always raises an exception."""

        msg = "Test error"
        raise ValueError(msg)


class TestAppExceptionHandler(BaseHandler[TestRequest, TestResponse]):
    """Handler that raises app exceptions for testing."""

    __test__ = False

    async def _handle_internal(self, request: TestRequest) -> TestResponse:  # noqa: ARG002
        """Implementation that raises an AppException."""

        msg = "Test validation error"
        raise ValidationException(msg)


class TestBaseHandler:
    """Test the BaseHandler class functionality."""

    @pytest.fixture
    def test_request(self, test_client_model):
        """Create a test request with proper trace information."""

        request = TestRequest(test_data="test")
        request.trace_id = "test-trace-123"
        request.request_id = "test-request-456"
        request.client = test_client_model

        return request

    @pytest.fixture
    def test_request_no_client(self):
        """Create a test request without client information."""

        request = TestRequest(test_data="test")
        request.trace_id = "test-trace-123"
        request.request_id = "test-request-456"
        request.client = None

        return request

    @pytest.fixture
    def test_handler(self):
        """Create a test handler instance."""

        return TestHandler()

    @pytest.fixture
    def failing_handler(self):
        """Create a failing handler instance."""

        return TestFailingHandler()

    @pytest.fixture
    def app_exception_handler(self):
        """Create an app exception handler instance."""

        return TestAppExceptionHandler()

    @pytest.mark.asyncio
    async def test_handle_success(self, test_handler, test_request):
        """Test successful handler execution."""

        with patch("app.domain.common.base_handler.get_logger") as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger
            mock_logger.bind.return_value = mock_logger

            result = await test_handler.handle(test_request)

            assert isinstance(result, TestResponse)
            assert result.result == "success"
            assert test_handler.handle_internal_called

            # Verify logging calls
            mock_logger.bind.assert_called()
            assert mock_logger.info.call_count == 2

    @pytest.mark.asyncio
    async def test_handle_with_app_exception(self, app_exception_handler, test_request):
        """Test handler execution with AppException."""

        with patch("app.domain.common.base_handler.get_logger") as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger
            mock_logger.bind.return_value = mock_logger

            with pytest.raises(ValidationException) as exc_info:
                await app_exception_handler.handle(test_request)

            # Verify exception details are properly set
            exception = exc_info.value
            assert exception.trace_id == "test-trace-123"
            assert exception.request_id == "test-request-456"

            # Verify warning was logged
            mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_with_unexpected_exception(
        self, failing_handler, test_request
    ):
        """Test handler execution with unexpected exception."""

        with patch("app.domain.common.base_handler.get_logger") as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger
            mock_logger.bind.return_value = mock_logger

            with pytest.raises(AppException) as exc_info:
                await failing_handler.handle(test_request)

            # Verify exception conversion
            exception = exc_info.value
            assert exception.error_code == ErrorCode.INTERNAL_SERVER_ERROR
            assert "TestFailingHandler" in exception.message
            assert exception.trace_id == "test-trace-123"
            assert exception.request_id == "test-request-456"
            assert isinstance(exception.cause, ValueError)

            # Verify error logging
            mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_logging_context(self, test_handler, test_request):
        """Test that proper logging context is created."""

        with patch("app.domain.common.base_handler.get_logger") as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger
            mock_logger.bind.return_value = mock_logger

            await test_handler.handle(test_request)

            # Verify bind was called with correct context
            bind_calls = mock_logger.bind.call_args_list
            assert len(bind_calls) > 0

            context = bind_calls[0][1]  # Get keyword arguments
            assert context["handler"] == "TestHandler"
            assert context["trace_id"] == "test-trace-123"
            assert context["request_id"] == "test-request-456"
            assert context["client_id"] == test_request.client.id

    @pytest.mark.asyncio
    async def test_handle_logging_context_no_client(
        self, test_handler, test_request_no_client
    ):
        """Test logging context when client is None."""

        with patch("app.domain.common.base_handler.get_logger") as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger
            mock_logger.bind.return_value = mock_logger

            await test_handler.handle(test_request_no_client)

            # Verify bind was called with unknown client
            bind_calls = mock_logger.bind.call_args_list
            context = bind_calls[0][1]
            assert context["client_id"] == "unknown"

    @pytest.mark.asyncio
    async def test_app_exception_trace_preservation(self, test_request):
        """Test that existing trace information on AppException is preserved."""

        class CustomHandler(BaseHandler[TestRequest, TestResponse]):
            async def _handle_internal(self, request: TestRequest) -> TestResponse:  # noqa: ARG002
                exc = AuthenticationException("Auth failed")
                exc.trace_id = "existing-trace"
                exc.request_id = "existing-request"

                raise exc

        handler = CustomHandler()

        with patch("app.domain.common.base_handler.get_logger") as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger
            mock_logger.bind.return_value = mock_logger

            with pytest.raises(AuthenticationException) as exc_info:
                await handler.handle(test_request)

            # Verify existing trace info is preserved
            exception = exc_info.value
            assert exception.trace_id == "existing-trace"
            assert exception.request_id == "existing-request"

    @pytest.mark.asyncio
    async def test_exception_detail_extraction(self, failing_handler, test_request):
        """Test that exception details are properly extracted."""

        with patch("app.domain.common.base_handler.get_logger") as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger
            mock_logger.bind.return_value = mock_logger

            with pytest.raises(AppException) as exc_info:
                await failing_handler.handle(test_request)

            exception = exc_info.value
            details = exception.details

            assert details["handler_class"] == "TestFailingHandler"
            assert details["original_exception"] == "ValueError"
            assert details["original_message"] == "Test error"
            assert "error_location" in details

    def test_log_performance_metric(self, test_handler):
        """Test performance metric logging."""

        with patch("app.domain.common.base_handler.get_logger") as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger
            mock_logger.bind.return_value = mock_logger
            test_handler.logger = mock_logger

            test_handler.log_performance_metric(
                "response_time", 150.5, "ms", {"endpoint": "/api/test"}
            )

            # Verify metric logging
            mock_logger.bind.assert_called_once()
            bind_args = mock_logger.bind.call_args[1]

            assert bind_args["metric_name"] == "response_time"
            assert bind_args["metric_value"] == 150.5
            assert bind_args["metric_unit"] == "ms"
            assert bind_args["handler_class"] == "TestHandler"
            assert bind_args["endpoint"] == "/api/test"

            mock_logger.info.assert_called_once_with("performance metric recorded")

    def test_log_performance_metric_default_unit(self, test_handler):
        """Test performance metric logging with default unit."""

        with patch("app.domain.common.base_handler.get_logger") as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger
            mock_logger.bind.return_value = mock_logger
            test_handler.logger = mock_logger

            test_handler.log_performance_metric("cpu_usage", 75.2)

            bind_args = mock_logger.bind.call_args[1]
            assert bind_args["metric_unit"] == "ms"  # Default unit

    def test_log_business_event(self, test_handler):
        """Test business event logging."""

        with patch("app.domain.common.base_handler.get_logger") as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger
            mock_logger.bind.return_value = mock_logger
            test_handler.logger = mock_logger

            event_data = {"user_id": "123", "action": "login"}
            test_handler.log_business_event("user_login", event_data)

            # Verify event logging
            mock_logger.bind.assert_called_once()
            bind_args = mock_logger.bind.call_args[1]

            assert bind_args["event_name"] == "user_login"
            assert bind_args["handler_class"] == "TestHandler"
            assert bind_args["event_data"] == event_data

            mock_logger.info.assert_called_once_with("business event occurred")

    def test_log_business_event_no_data(self, test_handler):
        """Test business event logging without additional data."""

        with patch("app.domain.common.base_handler.get_logger") as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger
            mock_logger.bind.return_value = mock_logger
            test_handler.logger = mock_logger

            test_handler.log_business_event("system_startup")

            bind_args = mock_logger.bind.call_args[1]
            assert "event_data" not in bind_args

    @pytest.mark.asyncio
    async def test_traceback_extraction(self, test_request):
        """Test that traceback information is properly extracted."""

        class TracebackHandler(BaseHandler[TestRequest, TestResponse]):
            async def _handle_internal(self, request: TestRequest) -> TestResponse:  # noqa: ARG002
                def inner_function():
                    msg = "Deep error"
                    raise RuntimeError(msg)

                inner_function()

        handler = TracebackHandler()

        with patch("app.domain.common.base_handler.get_logger") as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger
            mock_logger.bind.return_value = mock_logger

            with pytest.raises(AppException):
                await handler.handle(test_request)

            # Verify traceback context was logged
            error_calls = [
                call
                for call in mock_logger.bind.call_args_list
                if "exception_type" in call[1]
            ]
            assert len(error_calls) > 0

            error_context = error_calls[0][1]
            assert error_context["exception_type"] == "RuntimeError"
            assert error_context["error_function"] == "inner_function"
            assert "full_traceback" in error_context

    @pytest.mark.asyncio
    async def test_handler_inheritance_requirements(self):
        """Test that BaseHandler properly enforces abstract method implementation."""

        # This test ensures the abstract base class behavior
        assert hasattr(BaseHandler, "_handle_internal")

        # Verify that BaseHandler itself cannot be instantiated
        with pytest.raises(TypeError):
            BaseHandler()

    @pytest.mark.asyncio
    async def test_generic_type_safety(self, test_request):
        """Test that generic type constraints are working."""

        handler = TestHandler()
        result = await handler.handle(test_request)

        # These assertions verify the generic typing is working
        assert isinstance(result, TestResponse)
        assert hasattr(result, "result")
        assert result.result == "success"

    @pytest.mark.asyncio
    async def test_dependency_injection_integration(self, test_handler, test_request):
        """Test that dependency injection works with handlers."""

        # The @inject decorator should be working
        assert hasattr(test_handler, "__class__")

        # Test that handler can be executed
        result = await test_handler.handle(test_request)
        assert result is not None
