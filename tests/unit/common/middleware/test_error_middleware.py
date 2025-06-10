from unittest.mock import Mock, patch

import pytest
from fastapi import Response

from app.common.errors.errors import ApplicationError, ErrorCode
from app.common.middlewares.error_middleware import ErrorMiddleware


# noinspection PyUnusedLocal
class TestErrorHandlingMiddleware:
    """Test error handling middleware."""

    @pytest.fixture
    def middleware(self):
        """Create middleware instance."""
        return ErrorMiddleware(Mock())

    @pytest.fixture
    def mock_call_next(self):
        """Create mock call_next function."""

        async def call_next(request):  # noqa: ARG001
            return Response("OK", status_code=200)

        return call_next

    async def test_middleware_normal_request(
        self, middleware: ErrorMiddleware, mock_request, mock_call_next
    ):
        """Test middleware with normal request."""
        response = await middleware.dispatch(mock_request, mock_call_next)

        assert response.status_code == 200

    async def test_middleware_api_error(
        self, middleware: ErrorMiddleware, mock_request
    ):
        """Test middleware handling API errors."""

        async def call_next_with_error(request):  # noqa: ARG001
            msg = "Test API Error"
            raise ApplicationError(ErrorCode.CONFIGURATION_ERROR, msg, status_code=400)

        response = await middleware.dispatch(mock_request, call_next_with_error)

        assert response.status_code == 400

    async def test_middleware_unexpected_error(
        self, middleware: ErrorMiddleware, mock_request, suppress_logging
    ):
        """Test middleware handling unexpected errors."""

        async def call_next_with_exception(request):  # noqa: ARG001
            msg = "Unexpected error"
            raise ValueError(msg)

        with patch("app.common.logging.logger.logger", suppress_logging):
            response = await middleware.dispatch(mock_request, call_next_with_exception)

            assert response.status_code == 500

    async def test_middleware_request_validation_error(
        self, middleware: ErrorMiddleware, mock_request
    ):
        """Test middleware handling request validation errors."""
        from pydantic import ValidationError

        async def call_next_with_validation_error(request):  # noqa: ARG001
            msg = "Validation failed"
            raise ValidationError(msg, [])

        response = await middleware.dispatch(
            mock_request, call_next_with_validation_error
        )

        assert response.status_code == 422
