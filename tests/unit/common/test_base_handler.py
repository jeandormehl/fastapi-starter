# tests/unit/common/test_base_handler.py
from unittest.mock import Mock, patch

import pytest
from pydantic import BaseModel
from starlette.requests import Request

from app.common.base_handler import BaseHandler
from app.common.base_request import BaseRequest
from app.common.base_response import BaseResponse
from app.common.utils import PydiatorBuilder


class TestInput(BaseModel):
    __test__ = False
    data: dict[str, str]


class TestOutput(BaseModel):
    __test__ = False
    data: dict[str, str]


class TestRequest(BaseRequest):
    __test__ = False


class TestResponse(BaseResponse):
    __test__ = False


class ConcreteHandler(BaseHandler[TestRequest, TestResponse]):
    async def _handle_internal(self, request: TestRequest) -> TestResponse:
        return PydiatorBuilder.build(
            TestResponse,
            request.req,
            data=TestOutput(data={"processed": "other-value"}),
        )


class FailingHandler(BaseHandler[TestRequest, TestResponse]):
    async def _handle_internal(self, _request: TestRequest) -> TestResponse:
        msg = "Test error"
        raise ValueError(msg)


class TestBaseHandler:
    """Comprehensive tests for BaseHandler class."""

    @pytest.fixture
    def handler(self):
        return ConcreteHandler()

    @pytest.fixture
    def failing_handler(self):
        return FailingHandler()

    @pytest.fixture
    def test_request(self, mock_request):
        return PydiatorBuilder.build(
            TestRequest, mock_request, data={"processing": "value"}
        )

    @patch("app.common.base_handler.get_logger")
    def test_handler_initialization(self, mock_get_logger):
        """Test proper initialization of BaseHandler."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        handler = ConcreteHandler()

        mock_get_logger.assert_called_once_with("ConcreteHandler")
        assert handler.logger == mock_logger

    async def test_handle_success(self, handler, test_request):
        """Test successful request handling."""
        result = await handler.handle(test_request)

        assert isinstance(result, TestResponse)
        assert result.data.data == {"processed": "other-value"}

    async def test_handle_with_exception(self, failing_handler, test_request):
        """Test that exceptions are properly propagated."""
        with pytest.raises(ValueError, match="Test error"):
            await failing_handler.handle(test_request)

    @patch("app.common.base_handler.get_logger")
    def test_log_business_event_default_level(self, mock_get_logger):
        """Test business event logging with default level."""
        mock_logger = Mock()
        mock_bound_logger = Mock()
        mock_info_method = Mock()

        mock_logger.bind.return_value = mock_bound_logger
        mock_bound_logger.info = mock_info_method
        mock_get_logger.return_value = mock_logger

        handler = ConcreteHandler()
        handler.log_business_event("user_signup")

        expected_context = {
            "event_name": "user_signup",
            "event_type": "business_event",
            "handler_class": "ConcreteHandler",
        }

        mock_logger.bind.assert_called_once_with(**expected_context)
        mock_info_method.assert_called_once_with("business event: user_signup")

    @patch("app.common.base_handler.get_logger")
    def test_log_business_event_with_data_and_custom_level(self, mock_get_logger):
        """Test business event logging with event data and custom level."""
        mock_logger = Mock()
        mock_bound_logger = Mock()
        mock_warning_method = Mock()

        mock_logger.bind.return_value = mock_bound_logger
        mock_bound_logger.warning = mock_warning_method
        mock_get_logger.return_value = mock_logger

        handler = ConcreteHandler()
        event_data = {"user_id": 123, "plan": "premium"}
        handler.log_business_event("subscription_change", event_data, "warning")

        expected_context = {
            "event_name": "subscription_change",
            "event_type": "business_event",
            "handler_class": "ConcreteHandler",
            "event_data": event_data,
        }

        mock_logger.bind.assert_called_once_with(**expected_context)
        mock_warning_method.assert_called_once_with(
            "business event: subscription_change"
        )

    @patch("app.common.base_handler.get_logger")
    def test_log_performance_metric_default_unit(self, mock_get_logger):
        """Test performance metric logging with default unit."""
        mock_logger = Mock()
        mock_bound_logger = Mock()
        mock_info_method = Mock()

        mock_logger.bind.return_value = mock_bound_logger
        mock_bound_logger.info = mock_info_method
        mock_get_logger.return_value = mock_logger

        handler = ConcreteHandler()
        handler.log_performance_metric("database_query", 150.5)

        expected_context = {
            "metric_name": "database_query",
            "metric_value": 150.5,
            "metric_unit": "ms",
            "metric_type": "performance",
            "handler_class": "ConcreteHandler",
        }

        mock_logger.bind.assert_called_once_with(**expected_context)
        mock_info_method.assert_called_once_with("performance metric: database_query")

    @patch("app.common.base_handler.get_logger")
    def test_log_performance_metric_with_context(self, mock_get_logger):
        """Test performance metric logging with additional context."""
        mock_logger = Mock()
        mock_bound_logger = Mock()
        mock_info_method = Mock()

        mock_logger.bind.return_value = mock_bound_logger
        mock_bound_logger.info = mock_info_method
        mock_get_logger.return_value = mock_logger

        handler = ConcreteHandler()
        additional_context = {"query_type": "SELECT", "table": "users"}
        handler.log_performance_metric("db_query", 75.2, "seconds", additional_context)

        expected_context = {
            "metric_name": "db_query",
            "metric_value": 75.2,
            "metric_unit": "seconds",
            "metric_type": "performance",
            "handler_class": "ConcreteHandler",
            "query_type": "SELECT",
            "table": "users",
        }

        mock_logger.bind.assert_called_once_with(**expected_context)
        mock_info_method.assert_called_once_with("performance metric: db_query")

    @patch("app.common.base_handler.get_logger")
    def test_multiple_business_events_isolated(self, mock_get_logger):
        """Test that multiple business events are logged independently."""
        mock_logger = Mock()
        mock_bound_logger = Mock()
        mock_info_method = Mock()

        mock_logger.bind.return_value = mock_bound_logger
        mock_bound_logger.info = mock_info_method
        mock_get_logger.return_value = mock_logger

        handler = ConcreteHandler()

        handler.log_business_event("event1")
        handler.log_business_event("event2", {"data": "test"})

        assert mock_logger.bind.call_count == 2
        assert mock_info_method.call_count == 2

    async def test_handle_preserves_request_state(self, handler):
        """Test that handle method doesn't modify the original request."""
        original_data = TestInput(data={"original": "data"})
        req = Mock(spec=Request)
        req.state = Mock()
        req.state.trace_id = "trace_id"
        req.state.request_id = "request_id"

        request = PydiatorBuilder.build(TestRequest, req, data=original_data)

        await handler.handle(request)

        assert request.data == original_data

    @patch("app.common.base_handler.get_logger")
    def test_logger_name_matches_class_name(self, mock_get_logger):
        """Test that logger name correctly matches the handler class name."""

        class CustomNamedHandler(BaseHandler):
            async def _handle_internal(self, _request):
                return None

        CustomNamedHandler()
        mock_get_logger.assert_called_with("CustomNamedHandler")

    @patch("app.common.base_handler.get_logger")
    def test_log_business_event_none_data(self, mock_get_logger):
        """Test business event logging with None event data."""
        mock_logger = Mock()
        mock_bound_logger = Mock()
        mock_info_method = Mock()

        mock_logger.bind.return_value = mock_bound_logger
        mock_bound_logger.info = mock_info_method
        mock_get_logger.return_value = mock_logger

        handler = ConcreteHandler()
        handler.log_business_event("test_event", None)

        # Should not include event_data in context when None
        expected_context = {
            "event_name": "test_event",
            "event_type": "business_event",
            "handler_class": "ConcreteHandler",
        }

        mock_logger.bind.assert_called_once_with(**expected_context)

    @patch("app.common.base_handler.get_logger")
    def test_log_performance_metric_none_context(self, mock_get_logger):
        """Test performance metric logging with None additional context."""
        mock_logger = Mock()
        mock_bound_logger = Mock()
        mock_info_method = Mock()

        mock_logger.bind.return_value = mock_bound_logger
        mock_bound_logger.info = mock_info_method
        mock_get_logger.return_value = mock_logger

        handler = ConcreteHandler()
        handler.log_performance_metric("test_metric", 100.0, "ms", None)

        expected_context = {
            "metric_name": "test_metric",
            "metric_value": 100.0,
            "metric_unit": "ms",
            "metric_type": "performance",
            "handler_class": "ConcreteHandler",
        }

        mock_logger.bind.assert_called_once_with(**expected_context)
