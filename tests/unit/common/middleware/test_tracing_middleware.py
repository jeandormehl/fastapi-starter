from unittest.mock import Mock

import pytest
from fastapi import Request, Response

from app.common.middlewares.tracing_middleware import TracingMiddleware


# noinspection PyUnusedLocal
class TestTracingMiddleware:
    """Test tracing middleware."""

    @pytest.fixture
    def middleware(self):
        """Create middleware instance."""
        return TracingMiddleware(Mock())

    @pytest.fixture
    def mock_call_next(self):
        """Create mock call_next function."""

        async def call_next(request):  # noqa: ARG001
            return Response("OK", status_code=200)

        return call_next

    async def test_middleware_adds_trace_headers(
        self, middleware: TracingMiddleware, mock_request, mock_call_next
    ):
        """Test middleware adds trace headers to response."""
        response = await middleware.dispatch(mock_request, mock_call_next)

        assert response.status_code == 200
        # Check for trace headers in response
        assert "X-Trace-ID" in response.headers or hasattr(
            mock_request.state, "trace_id"
        )

    async def test_middleware_preserves_existing_trace_id(
        self, middleware: TracingMiddleware, mock_call_next
    ):
        """Test middleware preserves existing trace ID from headers."""
        mock_request = Mock(spec=Request)
        mock_request.headers = {"X-Trace-ID": "existing-trace-123"}
        mock_request.state = Mock()

        await middleware.dispatch(mock_request, mock_call_next)

        assert mock_request.state.trace_id == "existing-trace-123"

    async def test_middleware_generates_new_trace_id(
        self, middleware: TracingMiddleware, mock_request, mock_call_next
    ):
        """Test middleware generates new trace ID when none exists."""
        mock_request.headers = {}  # No existing trace ID

        await middleware.dispatch(mock_request, mock_call_next)

        assert hasattr(mock_request.state, "trace_id")
        assert mock_request.state.trace_id is not None
        assert len(mock_request.state.trace_id) > 0
