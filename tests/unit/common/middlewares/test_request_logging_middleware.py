from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.common.middlewares.request_logging_middleware import RequestLoggingMiddleware
from app.core.config import Configuration
from app.infrastructure.taskiq.task_manager import TaskManager


class TestRequestLoggingMiddlewareUnit:
    """Unit tests for RequestLoggingMiddleware components."""

    @pytest.fixture
    def middleware(self):
        """Create middleware instance for testing."""

        app = Mock()

        # Mock dependencies
        config = Mock()
        config.request_logging_enabled = True
        config.request_logging_log_headers = True
        config.request_logging_log_body = True
        config.request_logging_max_body_size = 10000
        config.request_logging_excluded_paths = ["/health"]
        config.request_logging_excluded_methods = ["OPTIONS"]

        task_manager = Mock()
        task_manager.submit_task = AsyncMock()

        logger = Mock()

        with patch("app.common.middlewares.request_logging_middleware.di") as mock_di:
            mock_di.__getitem__.side_effect = lambda key: {
                Configuration: config,
                TaskManager: task_manager,
                "timezone": "UTC",
            }[key]

            with patch(
                "app.common.middlewares.request_logging_middleware.get_logger",
                return_value=logger,
            ):
                middleware = RequestLoggingMiddleware(app)
                middleware.config = config
                middleware.task_manager = task_manager
                middleware.logger = logger
                return middleware

    async def test_should_process_request_enabled(self, middleware):
        """Test request processing decision when logging is enabled."""

        request = Mock()
        request.url.path = "/api/test"
        request.method = "GET"

        result = middleware._should_process_request(request)
        assert result is True

    async def test_should_process_request_disabled(self, middleware):
        """Test request processing decision when logging is disabled."""

        middleware.config.request_logging_enabled = False

        request = Mock()
        request.url.path = "/api/test"
        request.method = "GET"

        result = middleware._should_process_request(request)
        assert result is False

    async def test_should_process_request_excluded_path(self, middleware):
        """Test request processing decision for excluded paths."""

        request = Mock()
        request.url.path = "/health"
        request.method = "GET"

        result = middleware._should_process_request(request)
        assert result is False

    async def test_should_process_request_excluded_method(self, middleware):
        """Test request processing decision for excluded methods."""

        request = Mock()
        request.url.path = "/api/test"
        request.method = "OPTIONS"

        result = middleware._should_process_request(request)
        assert result is False

    async def test_extract_client_ip_forwarded(self, middleware):
        """Test client IP extraction with forwarded headers."""

        request = Mock()
        request.headers = {"x-forwarded-for": "192.168.1.1, 10.0.0.1"}
        request.client = None

        result = middleware._extract_client_ip(request)
        assert result == "192.168.1.1"

    async def test_extract_client_ip_real_ip(self, middleware):
        """Test client IP extraction with real IP header."""

        request = Mock()
        request.headers = {"x-real-ip": "192.168.1.1"}
        request.client = None

        result = middleware._extract_client_ip(request)
        assert result == "192.168.1.1"

    async def test_extract_client_ip_direct(self, middleware):
        """Test client IP extraction from direct client."""

        request = Mock()
        request.headers = {}
        request.client = Mock()
        request.client.host = "192.168.1.1"

        result = middleware._extract_client_ip(request)
        assert result == "192.168.1.1"

    async def test_categorize_error_client_error(self, middleware):
        """Test error categorization for client errors."""

        result = middleware._categorize_error(404)
        assert result == "client_error"

    async def test_categorize_error_server_error(self, middleware):
        """Test error categorization for server errors."""

        result = middleware._categorize_error(500)
        assert result == "server_error"

    async def test_should_capture_body_post_json(self, middleware):
        """Test body capture decision for POST with JSON."""

        request = Mock()
        request.method = "POST"
        request.headers = {"content-type": "application/json"}

        result = middleware._should_capture_body(request)
        assert result is True

    async def test_should_capture_body_get_request(self, middleware):
        """Test body capture decision for GET request."""

        request = Mock()
        request.method = "GET"
        request.headers = {"content-type": "application/json"}

        result = middleware._should_capture_body(request)
        assert result is False

    async def test_safe_read_request_body_success(self, middleware):
        """Test successful request body reading."""

        request = Mock()
        request.body = AsyncMock(return_value=b'{"test": "data"}')

        result = await middleware._safe_read_request_body(request)
        assert result == b'{"test": "data"}'

    async def test_safe_read_request_body_timeout(self, middleware):
        """Test request body reading with timeout."""

        request = Mock()
        request.body = AsyncMock(side_effect=TimeoutError())

        result = await middleware._safe_read_request_body(request)
        assert result == b""

    async def test_process_body_content_json(self, middleware):
        """Test body content processing for JSON."""

        body = b'{"test": "data", "number": 123}'

        result = await middleware._process_body_content(body, "request")

        assert result["type"] == "json"
        assert result["content"] == {"test": "data", "number": 123}
        assert result["size"] == len(body)

    async def test_process_body_content_text(self, middleware):
        """Test body content processing for plain text."""

        body = b"plain text content"

        result = await middleware._process_body_content(body, "request")

        assert result["type"] == "text"
        assert result["content"] == "plain text content"
        assert result["size"] == len(body)

    async def test_process_body_content_binary(self, middleware):
        """Test body content processing for binary data."""

        body = b"\x89PNG\r\n\x1a\n"  # PNG header

        result = await middleware._process_body_content(body, "request")

        assert result["type"] == "binary"
        assert "content" in result
        assert result["size"] == len(body)

    async def test_process_body_content_truncated(self, middleware):
        """Test body content processing with size limit."""

        middleware.config.request_logging_max_body_size = 10
        body = b"very long content that exceeds the limit"

        result = await middleware._process_body_content(body, "request")

        assert result["truncated"] is True
        assert result["original_size"] == len(body)
        assert result["captured_size"] == 10

    async def test_extract_enhanced_auth_info_authenticated(self, middleware):
        """Test authentication info extraction for authenticated request."""

        request = Mock()

        # Mock authenticated client
        client = Mock()
        client.client_id = "test-client"
        client.auth_method = "bearer"
        request.state.client = client

        # Mock scopes
        scope1 = Mock()
        scope1.name = "read"
        scope2 = Mock()
        scope2.name = "write"
        request.state.scopes = [scope1, scope2]

        # Mock auth header
        request.headers = {"authorization": "Bearer token123"}

        result = middleware._extract_enhanced_auth_info(request)

        assert result["authenticated"] is True
        assert result["client_id"] == "test-client"
        assert result["auth_method"] == "bearer"
        assert result["scopes"] == ["read", "write"]
        assert result["has_bearer_token"] is True

    async def test_extract_enhanced_auth_info_unauthenticated(self, middleware):
        """Test authentication info extraction for unauthenticated request."""

        request = Mock()
        request.state = Mock()
        request.headers = {}

        # Remove authentication attributes
        delattr(request.state, "client") if hasattr(request.state, "client") else None
        delattr(request.state, "scopes") if hasattr(request.state, "scopes") else None

        result = middleware._extract_enhanced_auth_info(request)

        assert result["authenticated"] is False
        assert result["client_id"] is None
        assert result["scopes"] == []
        assert result["auth_method"] is None
        assert "has_bearer_token" not in result

    async def test_get_middleware_stats(self, middleware):
        """Test middleware statistics collection."""

        # Simulate some activity
        middleware._request_count = 100
        middleware._error_count = 5
        middleware._skip_count = 20

        stats = await middleware.get_middleware_stats()

        assert stats["total_requests_processed"] == 100
        assert stats["total_errors"] == 5
        assert stats["total_skipped"] == 20
        assert stats["error_rate"] == 0.05
        assert stats["skip_rate"] == 20 / 120  # skip_count / (requests + skips)
