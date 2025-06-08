import uuid
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from app.common.middlewares.tracing_middleware import TracingMiddleware


class TestTracingMiddleware:
    """Comprehensive test suite for TracingMiddleware."""

    @pytest.fixture
    def mock_app(self):
        """Create a mock ASGI application."""

        return Mock(spec=ASGIApp)

    @pytest.fixture
    def middleware(self, mock_app):
        """Create TracingMiddleware instance for testing."""

        return TracingMiddleware(mock_app)

    @pytest.fixture
    def mock_call_next(self):
        """Mock call_next function for middleware testing."""

        return AsyncMock()

    @pytest.fixture
    def sample_response(self):
        """Create a sample response for testing."""

        return JSONResponse({"message": "success"}, status_code=200)

    @pytest.fixture
    def mock_request_with_trace_header(self, mock_request):
        """Create request with existing trace header."""

        mock_request.headers = {
            **dict(mock_request.headers),
            "x-trace-id": "550e8400-e29b-41d4-a716-446655440000",
        }
        return mock_request

    @pytest.mark.asyncio
    async def test_dispatch_generates_new_trace_id(
        self, middleware, mock_request, mock_call_next, sample_response
    ):
        """Test trace ID generation when no header is present."""

        mock_call_next.return_value = sample_response

        result = await middleware.dispatch(mock_request, mock_call_next)

        # Verify trace context was set in request state
        assert hasattr(mock_request.state, "trace_id")
        assert hasattr(mock_request.state, "request_id")

        # Verify both IDs are valid UUIDs
        trace_uuid = uuid.UUID(mock_request.state.trace_id)
        request_uuid = uuid.UUID(mock_request.state.request_id)

        assert isinstance(trace_uuid, uuid.UUID)
        assert isinstance(request_uuid, uuid.UUID)

        # Verify different IDs were generated
        assert mock_request.state.trace_id != mock_request.state.request_id

        # Verify headers were added to response
        assert "X-Trace-ID" in result.headers
        assert "X-Request-ID" in result.headers
        assert result.headers["X-Trace-ID"] == mock_request.state.trace_id
        assert result.headers["X-Request-ID"] == mock_request.state.request_id

    @pytest.mark.asyncio
    async def test_dispatch_preserves_existing_trace_id(
        self,
        middleware,
        mock_request_with_trace_header,
        mock_call_next,
        sample_response,
    ):
        """Test preservation of existing trace ID from headers."""

        expected_trace_id = "550e8400-e29b-41d4-a716-446655440000"
        mock_call_next.return_value = sample_response

        result = await middleware.dispatch(
            mock_request_with_trace_header, mock_call_next
        )

        # Verify existing trace ID was preserved
        assert mock_request_with_trace_header.state.trace_id == expected_trace_id

        # Verify new request ID was generated
        request_uuid = uuid.UUID(mock_request_with_trace_header.state.request_id)
        assert isinstance(request_uuid, uuid.UUID)

        # Verify headers match state
        assert result.headers["X-Trace-ID"] == expected_trace_id
        assert (
            result.headers["X-Request-ID"]
            == mock_request_with_trace_header.state.request_id
        )

    @pytest.mark.asyncio
    async def test_security_headers_added(
        self, middleware, mock_request, mock_call_next, sample_response
    ):
        """Test that all security headers are properly added."""

        mock_call_next.return_value = sample_response

        result = await middleware.dispatch(mock_request, mock_call_next)

        # Verify all expected security headers
        expected_security_headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        }

        for header_name, expected_value in expected_security_headers.items():
            assert header_name in result.headers
            assert result.headers[header_name] == expected_value

    def test_get_trace_id_from_various_headers(self, middleware, mock_request):
        """Test trace ID extraction from different header variations."""

        header_variations = [
            ("x-trace-id", "trace-123"),
            ("trace-id", "trace-456"),
            ("x-correlation-id", "corr-789"),
            ("correlation-id", "corr-abc"),
            ("X-TRACE-ID", "trace-upper"),  # Case insensitive
            ("CORRELATION-ID", "corr-upper"),
        ]

        for header_name, _header_value in header_variations:
            # Create UUID for test
            test_uuid = str(uuid.uuid4())
            mock_request.headers = {header_name: test_uuid}

            trace_id = middleware._get_trace_id(mock_request)
            assert trace_id == test_uuid

    def test_get_trace_id_no_headers(self, middleware, mock_request):
        """Test trace ID generation when no relevant headers exist."""

        mock_request.headers = {
            "user-agent": "test-agent",
            "content-type": "application/json",
            "authorization": "Bearer token",
        }

        trace_id = middleware._get_trace_id(mock_request)

        # Should generate new UUID
        trace_uuid = uuid.UUID(trace_id)
        assert isinstance(trace_uuid, uuid.UUID)

    def test_get_trace_id_empty_headers(self, middleware, mock_request):
        """Test trace ID generation with empty headers."""

        mock_request.headers = {}

        trace_id = middleware._get_trace_id(mock_request)

        # Should generate new UUID
        trace_uuid = uuid.UUID(trace_id)
        assert isinstance(trace_uuid, uuid.UUID)

    def test_get_trace_id_case_insensitive_matching(self, middleware, mock_request):
        """Test case-insensitive header matching."""

        test_uuid = str(uuid.uuid4())
        case_variations = [
            "x-trace-id",
            "X-Trace-ID",
            "X-TRACE-ID",
            "x-TRACE-id",
            "X-trace-ID",
        ]

        for header_name in case_variations:
            mock_request.headers = {header_name: test_uuid}

            trace_id = middleware._get_trace_id(mock_request)
            assert trace_id == test_uuid

    def test_add_trace_headers_comprehensive(self, middleware):
        """Test comprehensive header addition."""

        response = JSONResponse({"test": "data"})
        test_trace_id = str(uuid.uuid4())
        test_request_id = str(uuid.uuid4())

        middleware._add_trace_headers(response, test_trace_id, test_request_id)

        # Verify tracing headers
        assert response.headers["X-Trace-ID"] == test_trace_id
        assert response.headers["X-Request-ID"] == test_request_id

        # Verify security headers
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["X-XSS-Protection"] == "1; mode=block"
        assert (
            response.headers["Strict-Transport-Security"]
            == "max-age=31536000; includeSubDomains"
        )

    def test_add_trace_headers_preserves_existing(self, middleware):
        """Test that adding trace headers preserves existing response headers."""

        response = JSONResponse({"test": "data"})
        response.headers["Custom-Header"] = "custom-value"
        response.headers["Content-Type"] = "application/json"

        test_trace_id = str(uuid.uuid4())
        test_request_id = str(uuid.uuid4())

        middleware._add_trace_headers(response, test_trace_id, test_request_id)

        # Verify existing headers are preserved
        assert response.headers["Custom-Header"] == "custom-value"
        assert response.headers["Content-Type"] == "application/json"

        # Verify new headers were added
        assert response.headers["X-Trace-ID"] == test_trace_id
        assert response.headers["X-Request-ID"] == test_request_id

    @pytest.mark.asyncio
    async def test_request_id_uniqueness(
        self, middleware, mock_request, mock_call_next, sample_response
    ):
        """Test that request ID is unique for each request."""

        mock_call_next.return_value = sample_response

        request_ids = []

        # Process multiple requests
        for _ in range(10):
            # Reset request state
            mock_request.state = Mock()

            await middleware.dispatch(mock_request, mock_call_next)
            request_ids.append(mock_request.state.request_id)

        # Verify all request IDs are unique
        assert len(set(request_ids)) == len(request_ids)

        # Verify all are valid UUIDs
        for request_id in request_ids:
            uuid.UUID(request_id)

    @pytest.mark.asyncio
    async def test_trace_id_consistency_with_header(
        self, middleware, mock_request, mock_call_next, sample_response
    ):
        """Test trace ID consistency when provided in header."""

        expected_trace_id = str(uuid.uuid4())
        mock_request.headers = {"x-trace-id": expected_trace_id}
        mock_call_next.return_value = sample_response

        result = await middleware.dispatch(mock_request, mock_call_next)

        # Verify trace ID consistency throughout the request
        assert mock_request.state.trace_id == expected_trace_id
        assert result.headers["X-Trace-ID"] == expected_trace_id

    @pytest.mark.asyncio
    async def test_multiple_correlation_headers(
        self, middleware, mock_request, mock_call_next, sample_response
    ):
        """Test behavior when multiple correlation headers are present."""

        trace_uuid_1 = str(uuid.uuid4())
        trace_uuid_2 = str(uuid.uuid4())

        # Set multiple trace headers (first valid one should be used)
        mock_request.headers = {
            "x-trace-id": trace_uuid_1,
            "correlation-id": trace_uuid_2,
            "x-correlation-id": "invalid-uuid",
        }
        mock_call_next.return_value = sample_response

        result = await middleware.dispatch(mock_request, mock_call_next)

        # Should use the first valid UUID found
        assert mock_request.state.trace_id == trace_uuid_1
        assert result.headers["X-Trace-ID"] == trace_uuid_1

    @pytest.mark.asyncio
    async def test_header_priority_order(
        self, middleware, mock_request, mock_call_next, sample_response
    ):
        """Test header priority order for trace ID extraction."""

        # Set headers in reverse priority order
        trace_uuid_highest = str(uuid.uuid4())
        trace_uuid_lower = str(uuid.uuid4())

        mock_request.headers = {
            "correlation-id": trace_uuid_lower,  # Lower priority
            "x-trace-id": trace_uuid_highest,  # Higher priority
        }
        mock_call_next.return_value = sample_response

        await middleware.dispatch(mock_request, mock_call_next)

        # Should use x-trace-id (higher priority)
        assert mock_request.state.trace_id == trace_uuid_highest

    @pytest.mark.asyncio
    async def test_state_isolation_between_requests(
        self, middleware, mock_call_next, sample_response
    ):
        """Test that request state is isolated between different requests."""
        mock_call_next.return_value = sample_response

        # Create two separate request objects
        request1 = Mock(spec=Request)
        request1.headers = {"x-trace-id": str(uuid.uuid4())}
        request1.state = Mock()

        request2 = Mock(spec=Request)
        request2.headers = {"x-trace-id": str(uuid.uuid4())}
        request2.state = Mock()

        # Process both requests
        await middleware.dispatch(request1, mock_call_next)
        await middleware.dispatch(request2, mock_call_next)

        # Verify state isolation
        assert request1.state.trace_id != request2.state.trace_id
        assert request1.state.request_id != request2.state.request_id

        # Verify both have valid UUIDs
        uuid.UUID(request1.state.trace_id)
        uuid.UUID(request1.state.request_id)
        uuid.UUID(request2.state.trace_id)
        uuid.UUID(request2.state.request_id)
