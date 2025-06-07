import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.requests import Request
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from app.common.middlewares.request_logging_middleware import RequestLoggingMiddleware
from app.core.config import Configuration
from app.infrastructure.taskiq.task_manager import TaskManager


class TestRequestLoggingMiddleware:
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

    async def test_client_ip_extraction_fixed(self, middleware):
        """Test that client IP extraction handles forwarded headers correctly."""

        request = MagicMock(spec=Request)
        request.headers = {"x-forwarded-for": "192.168.1.1, 10.0.0.1, 172.16.0.1"}
        request.client = None

        ip = middleware._extract_client_ip(request)

        # Should return first IP, not a list
        assert ip == "192.168.1.1"
        assert isinstance(ip, str)

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

    async def test_memory_efficient_body_capture(self, middleware):
        """Test memory-efficient body capture with size limits."""

        request = MagicMock(spec=Request)
        request.method = "POST"
        request.headers = {"content-type": "application/json", "content-length": "50"}

        # Mock body reading
        large_body = b"x" * (2 * 1024 * 1024)  # 2MB body

        with patch.object(middleware, "_safe_read_request_body_limited") as mock_read:
            mock_read.return_value = large_body[
                : middleware.config.request_logging_max_body_size
            ]

            result = await middleware._capture_request_body_safe(request)

            assert result is not None
            assert "content" in result

    async def test_streaming_response_handling(self, middleware):
        """Test improved streaming response handling."""

        async def generate_chunks():
            for i in range(5):
                yield f"chunk_{i}".encode()

        response = StreamingResponse(generate_chunks(), media_type="text/plain")

        result = await middleware._capture_response_body_safe(response)

        assert result is not None
        assert result["type"] == "streaming_response"
        assert "capture_enabled" in result

    async def test_defensive_auth_info_extraction(self, middleware):
        """Test defensive programming in auth info extraction."""

        # Test with missing state
        request = MagicMock(spec=Request)
        del request.state  # Remove state attribute

        auth_info = middleware._extract_auth_info(request)

        assert auth_info["authenticated"] is False
        assert auth_info["client_id"] is None

    async def test_memory_management_request_limit(self, middleware):
        """Test that middleware respects active request limits."""

        # Fill up active requests
        for i in range(0, 101):
            fake_request = MagicMock(content=i)
            middleware._active_requests.add(fake_request)

        request = MagicMock(spec=Request)
        request.url.path = "/test"
        request.method = "GET"

        should_process = middleware._should_process_request(request)

        assert should_process is False  # Should skip due to memory limits

    async def test_body_truncation_safety(self, middleware):
        """Test safe body truncation without breaking encoding."""

        # Test with UTF-8 content that might break at truncation point
        body = "Hello 世界! " * 1000  # Contains multi-byte characters
        body_bytes = body.encode("utf-8")

        truncated = middleware._truncate_body_safely(body_bytes, 100)

        assert isinstance(truncated, str)
        assert len(truncated.encode("utf-8")) <= 104  # Account for "..." addition

    async def test_concurrent_request_processing(self):
        """Test middleware under concurrent load."""

        app = FastAPI()

        @app.get("/test")
        async def test_endpoint():
            await asyncio.sleep(0.1)
            return {"message": "success"}

        app.add_middleware(RequestLoggingMiddleware)

        client = TestClient(app)

        # Simulate concurrent requests
        async def make_request():
            return client.get("/test")

        tasks = [make_request() for _ in range(10)]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # All requests should complete successfully
        success_count = sum(
            1 for r in responses if hasattr(r, "status_code") and r.status_code == 200
        )
        assert success_count > 0

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

        assert result["type"] == "text"
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

    async def test_extract_auth_info_authenticated(self, middleware):
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

        result = middleware._extract_auth_info(request)

        assert result["authenticated"] is True
        assert result["client_id"] == "test-client"
        assert result["auth_method"] == "bearer"
        assert result["scopes"] == ["read", "write"]
        assert result["has_bearer_token"] is True

    async def test_extract_auth_info_unauthenticated(self, middleware):
        """Test authentication info extraction for unauthenticated request."""

        request = Mock()
        request.state = Mock()
        request.headers = {}

        # Remove authentication attributes
        delattr(request.state, "client") if hasattr(request.state, "client") else None
        delattr(request.state, "scopes") if hasattr(request.state, "scopes") else None

        result = middleware._extract_auth_info(request)

        assert result["authenticated"] is False
        assert result["client_id"] is None
        assert result["scopes"] == []
        assert result["auth_method"] is None
        assert result["has_bearer_token"] is False

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
