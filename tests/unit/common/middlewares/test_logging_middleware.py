# tests/unit/common/middlewares/test_logging_middleware_enhanced.py
import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
from prisma.models import Scope
from starlette.responses import Response
from starlette.types import ASGIApp

from app.common.middlewares.logging_middleware import LoggingMiddleware
from app.core.config import Configuration
from app.infrastructure.taskiq.task_manager import TaskManager


class MockConfiguration:
    """Mock configuration for testing."""

    def __init__(self):
        self.request_logging_enabled = True
        self.request_logging_log_headers = True
        self.request_logging_excluded_paths = []
        self.request_logging_excluded_methods = []
        self.service_version = "1.0.0"


class MockRequest:
    """Mock request for testing."""

    # noinspection HttpUrlsUsage
    def __init__(self, method="GET", path="/test"):
        self.method = method
        self.url = Mock()
        self.url.path = path
        self.url.base_url = "http://test.com"
        self.query_params = {}
        self.headers = {}
        self.client = Mock()
        self.client.host = "127.0.0.1"
        self.state = Mock()
        self.state.client = Mock()
        self.state.client.client_id = "client-id"

        scope = Mock(spec=Scope)
        scope.name = "test"
        self.state.client.scopes = [scope]


class TestLoggingMiddleware:
    """Enhanced tests for LoggingMiddleware."""

    @pytest.fixture
    def mock_config(self):
        return MockConfiguration()

    @pytest.fixture
    def mock_task_manager(self):
        task_manager = Mock(spec=TaskManager)
        task_manager.submit_task = AsyncMock()
        return task_manager

    @pytest.fixture
    def mock_logger(self):
        logger = Mock()
        logger.bind.return_value = logger
        return logger

    @pytest.fixture
    def middleware(self, mock_config, mock_task_manager, mock_logger):
        app = Mock(spec=ASGIApp)
        with patch("kink.di") as mock_di:
            mock_di.__getitem__.side_effect = lambda key: {
                Configuration: mock_config,
                TaskManager: mock_task_manager,
                "timezone": Mock(),
            }[key]

            with patch(
                "app.common.middlewares.logging_middleware.get_logger",
                return_value=mock_logger,
            ):
                return LoggingMiddleware(app)

    async def test_successful_request_processing(self, middleware, mock_logger):
        """Test successful request processing with full logging."""
        request = MockRequest()
        request.headers = {
            "content-type": "application/json",
            "user-agent": "TestAgent",
        }

        async def mock_call_next(_req):
            await asyncio.sleep(0.01)  # Simulate processing time
            _response = Response(content="OK", status_code=200)
            _response.headers["content-length"] = "2"
            return _response

        with (
            patch("time.time", side_effect=[1000.0, 1000.1]),  # 100ms duration
            patch(
                "app.common.middlewares.logging_middleware.datetime"
            ) as mock_datetime,
        ):
            mock_start = Mock()
            mock_end = Mock()
            mock_datetime.now.side_effect = [mock_start, mock_end]

            response = await middleware.dispatch(request, mock_call_next)

            assert response.status_code == 200
            assert "X-Response-Time" in response.headers
            assert response.headers["X-Response-Time"] == "0.100s"

            # Verify logging calls
            assert mock_logger.bind.call_count >= 2  # Start and completion

    async def test_skip_health_check_endpoints(self, middleware, mock_logger):
        """Test that health check endpoints are skipped."""
        request = MockRequest(path="/v1/health")

        async def mock_call_next(_req):
            return Response(content="OK", status_code=200)

        response = await middleware.dispatch(request, mock_call_next)

        assert response.status_code == 200
        # No logging should occur for health checks
        mock_logger.bind.assert_not_called()

    async def test_skip_docs_endpoints(self, middleware, mock_logger):
        """Test that documentation endpoints are skipped."""
        paths_to_skip = ["/v1/docs", "/v1/redoc", "/v1/openapi.json"]

        for path in paths_to_skip:
            request = MockRequest(path=path)

            async def mock_call_next(_req):
                return Response(content="OK", status_code=200)

            response = await middleware.dispatch(request, mock_call_next)
            assert response.status_code == 200

        # No logging should occur for any of these
        mock_logger.bind.assert_not_called()

    async def test_skip_static_files(self, middleware, mock_logger):
        """Test that static file requests are skipped."""
        request = MockRequest(path="/static/css/style.css")

        async def mock_call_next(_req):
            return Response(content="CSS", status_code=200)

        response = await middleware.dispatch(request, mock_call_next)

        assert response.status_code == 200
        mock_logger.bind.assert_not_called()

    async def test_error_response_categorization(self, middleware, mock_logger):
        """Test error response categorization."""
        request = MockRequest()

        async def mock_call_next(_req):
            return Response(content="Not Found", status_code=404)

        with (
            patch("time.time", side_effect=[1000.0, 1000.05]),
            patch(
                "app.common.middlewares.logging_middleware.datetime"
            ) as mock_datetime,
        ):
            mock_datetime.now.return_value = Mock()

            response = await middleware.dispatch(request, mock_call_next)

            assert response.status_code == 404

            # Check that error categorization was logged
            completion_call = None
            for call in mock_logger.bind.call_args_list:
                call_kwargs = call[1]
                if call_kwargs.get("event") == "request_completed":
                    completion_call = call_kwargs
                    break

            assert completion_call is not None
            assert completion_call["error_occurred"] is True
            assert completion_call["error_category"] == "not_found"
            assert completion_call["success"] is False

    async def test_authentication_context_extraction(self, middleware, mock_logger):
        """Test authentication context extraction."""
        request = MockRequest()
        request.headers["authorization"] = "Bearer token123"
        request.state.client = Mock()
        request.state.client.client_id = "app123"
        request.state.client.scopes = [Mock(name="read"), Mock(name="write")]

        async def mock_call_next(_req):
            return Response(content="OK", status_code=200)

        with (
            patch("time.time", side_effect=[1000.0, 1000.01]),
            patch(
                "app.common.middlewares.logging_middleware.datetime"
            ) as mock_datetime,
        ):
            mock_datetime.now.return_value = Mock()

            await middleware.dispatch(request, mock_call_next)

            # Find the request start log call
            start_call = None
            for call in mock_logger.bind.call_args_list:
                call_kwargs = call[1]
                if call_kwargs.get("event") == "request_started":
                    start_call = call_kwargs
                    break

            assert start_call is not None
            assert start_call["authenticated"] is True
            assert start_call["client_id"] == "app123"
            assert start_call["has_bearer_token"] is True
            assert start_call["auth_method"] == "jwt_bearer"

    async def test_database_logging_disabled(self, middleware, mock_task_manager):
        """Test behavior when database logging is disabled."""
        middleware.config.request_logging_enabled = False
        request = MockRequest()

        async def mock_call_next(_req):
            return Response(content="OK", status_code=200)

        with (
            patch("time.time", side_effect=[1000.0, 1000.01]),
            patch(
                "app.common.middlewares.logging_middleware.datetime"
            ) as mock_datetime,
        ):
            mock_datetime.now.return_value = Mock()

            await middleware.dispatch(request, mock_call_next)

            # No task should be submitted
            mock_task_manager.submit_task.assert_not_called()

    async def test_client_ip_extraction(self, middleware, mock_logger):  # noqa: ARG002
        """Test client IP extraction with different scenarios."""
        request = MockRequest()
        request.client = None  # No client info

        async def mock_call_next(_req):
            return Response(content="OK", status_code=200)

        with (
            patch("time.time", side_effect=[1000.0, 1000.01]),
            patch(
                "app.common.middlewares.logging_middleware.datetime"
            ) as mock_datetime,
        ):
            mock_datetime.now.return_value = Mock()

            with patch(
                "app.common.middlewares.logging_middleware.ClientIPExtractor"
            ) as mock_extractor:
                mock_extractor.extract_client_ip.return_value = "unknown"

                await middleware.dispatch(request, mock_call_next)

                mock_extractor.extract_client_ip.assert_called_once_with(request)

    async def test_middleware_exception_propagation(self, middleware, mock_logger):
        """Test that non-logging exceptions are properly propagated."""
        request = MockRequest()

        async def mock_call_next(_req):
            msg = "Downstream error"
            raise ValueError(msg)

        with pytest.raises(ValueError, match="Downstream error"):
            await middleware.dispatch(request, mock_call_next)

        # Should log middleware error but still propagate
        error_logged = any(
            "logging middleware encountered an error" in str(call)
            for call in mock_logger.bind.return_value.error.call_args_list
        )
        assert error_logged

    async def test_safe_int_conversion(self, middleware):
        """Test _safe_int utility method."""
        assert middleware._safe_int("123") == 123
        assert middleware._safe_int("0") == 0
        assert middleware._safe_int(None) is None
        assert middleware._safe_int("invalid") is None
        assert middleware._safe_int("") is None

    async def test_middleware_stats(self, middleware):
        """Test middleware statistics collection."""
        request1 = MockRequest(path="/api/test")
        request2 = MockRequest(path="/v1/health")  # Should be skipped

        async def mock_call_next(_req):
            return Response(content="OK", status_code=200)

        with (
            patch("time.time", side_effect=[1000.0, 1000.01, 1000.02, 1000.03]),
            patch(
                "app.common.middlewares.logging_middleware.datetime"
            ) as mock_datetime,
        ):
            mock_datetime.now.return_value = Mock()

            await middleware.dispatch(request1, mock_call_next)
            await middleware.dispatch(request2, mock_call_next)

            stats = await middleware.get_middleware_stats()

            assert stats["total_requests_processed"] == 1
            assert stats["total_skipped"] == 1
            assert stats["skip_rate"] == 0.5

    async def test_excluded_paths_configuration(self, middleware, mock_logger):
        """Test custom excluded paths configuration."""
        middleware.config.request_logging_excluded_paths = ["/admin", "/internal"]

        for path in ["/admin/users", "/internal/metrics"]:
            request = MockRequest(path=path)

            async def mock_call_next(_req):
                return Response(content="OK", status_code=200)

            response = await middleware.dispatch(request, mock_call_next)
            assert response.status_code == 200

        # No logging should occur
        mock_logger.bind.assert_not_called()

    async def test_excluded_methods_configuration(self, middleware, mock_logger):
        """Test custom excluded methods configuration."""
        middleware.config.request_logging_excluded_methods = ["OPTIONS", "HEAD"]

        for method in ["OPTIONS", "HEAD"]:
            request = MockRequest(method=method, path="/api/test")

            async def mock_call_next(_req):
                return Response(content="", status_code=200)

            response = await middleware.dispatch(request, mock_call_next)
            assert response.status_code == 200

        # No logging should occur
        mock_logger.bind.assert_not_called()
