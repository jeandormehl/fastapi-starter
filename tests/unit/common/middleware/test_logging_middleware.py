from unittest.mock import Mock, patch

import pytest
from fastapi import Response

from app.common.middlewares.logging_middleware import LoggingMiddleware


# noinspection PyUnusedLocal
class TestLoggingMiddleware:
    """Test logging middleware."""

    @pytest.fixture
    def middleware(self):
        """Create middleware instance."""
        return LoggingMiddleware(Mock())

    @pytest.fixture
    def mock_call_next(self):
        """Create mock call_next function."""

        async def call_next(request):  # noqa: ARG001
            return Response("OK", status_code=200)

        return call_next

    async def test_middleware_logs_request(
        self,
        middleware: LoggingMiddleware,
        mock_request,
        mock_call_next,
        suppress_logging,
    ):
        """Test middleware logs request information."""
        with patch("app.common.logging.logger.logger", suppress_logging) as mock_logger:
            response = await middleware.dispatch(mock_request, mock_call_next)

            assert response.status_code == 200
            assert mock_logger.bind.call_count > 0
            assert mock_logger.info.call_count > 0

    async def test_middleware_adds_trace_context(
        self, middleware: LoggingMiddleware, mock_request, mock_call_next
    ):
        """Test middleware adds trace context to request."""
        await middleware.dispatch(mock_request, mock_call_next)

        # Check that trace context was added to request state
        assert hasattr(mock_request.state, "trace_id")
        assert hasattr(mock_request.state, "request_id")

    async def test_middleware_measures_duration(
        self, middleware: LoggingMiddleware, mock_request, suppress_logging
    ):
        """Test middleware measures request duration."""

        async def slow_call_next(request):  # noqa: ARG001
            import asyncio

            await asyncio.sleep(0.1)  # Simulate slow operation
            return Response("OK", status_code=200)

        with patch("app.common.logging.logger.logger", suppress_logging):
            response = await middleware.dispatch(mock_request, slow_call_next)

            assert response.status_code == 200
