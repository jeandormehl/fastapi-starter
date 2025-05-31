import asyncio
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.api.middlewares.request_middleware import RequestMiddleware
from app.core.errors.exceptions import (
    AppException,
    AuthenticationException,
    ErrorCode,
    ValidationException,
)


# noinspection PyUnusedLocal
class TestRequestMiddleware:
    """Comprehensive test suite for RequestMiddleware."""

    @pytest.fixture
    def mock_app(self):
        """Create a mock ASGI app."""

        return MagicMock(spec=ASGIApp)

    @pytest.fixture
    def middleware(self, mock_app):
        """Create RequestMiddleware instance."""

        return RequestMiddleware(mock_app)

    @pytest.fixture
    def mock_response(self):
        """Create a mock response."""

        response = MagicMock(spec=Response)
        response.status_code = 200
        response.headers = {}

        return response

    @pytest.fixture
    def mock_call_next(self, mock_response):
        """Create mock call_next function."""

        async def call_next(request: Request):  # noqa: ARG001
            return mock_response

        return call_next

    @pytest.fixture
    def mock_request_with_trace(self, mock_request):
        """Create mock request with trace headers."""

        trace_id = str(uuid.uuid4())
        mock_request.headers = {
            "x-trace-id": trace_id,
            "user-agent": "test-agent/1.0",
            "content-type": "application/json",
            "content-length": "100",
        }

        return mock_request

    @pytest.mark.asyncio
    async def test_successful_request_processing(
        self, middleware, mock_request, mock_call_next, mock_response
    ):
        """Test successful request processing with comprehensive logging."""

        with patch.object(middleware, "_logger") as mock_logger:
            mock_bound_logger = Mock()
            mock_logger.bind.return_value = mock_bound_logger

            # Execute middleware
            response = await middleware.dispatch(mock_request, mock_call_next)

            # Verify response headers are added
            assert "X-Trace-ID" in response.headers
            assert "X-Request-ID" in response.headers
            assert "X-Response-Time" in response.headers

            # Verify trace information is set on request state
            assert hasattr(mock_request.state, "trace_id")
            assert hasattr(mock_request.state, "request_id")
            assert hasattr(mock_request.state, "start_time")

            # Verify response is returned unchanged otherwise
            assert response == mock_response

    @pytest.mark.asyncio
    async def test_trace_id_from_header(
        self, middleware, mock_request_with_trace, mock_call_next
    ):
        """Test that trace_id is extracted from request headers."""

        with patch.object(middleware, "_logger") as mock_logger:
            mock_bound_logger = Mock()
            mock_logger.bind.return_value = mock_bound_logger

            original_trace_id = mock_request_with_trace.headers["x-trace-id"]

            response = await middleware.dispatch(
                mock_request_with_trace, mock_call_next
            )

            # Verify the trace_id from header is used
            assert response.headers["X-Trace-ID"] == original_trace_id
            assert mock_request_with_trace.state.trace_id == original_trace_id

    @pytest.mark.asyncio
    async def test_trace_id_generation_when_missing(
        self, middleware, mock_request, mock_call_next
    ):
        """Test that trace_id is generated when not provided in headers."""

        with patch.object(middleware, "_logger") as mock_logger:
            mock_bound_logger = Mock()
            mock_logger.bind.return_value = mock_bound_logger

            # Ensure no trace headers
            mock_request.headers = {}

            response = await middleware.dispatch(mock_request, mock_call_next)

            # Verify a valid UUID is generated
            trace_id = response.headers["X-Trace-ID"]
            assert uuid.UUID(trace_id)  # Should not raise ValueError
            assert mock_request.state.trace_id == trace_id

    @pytest.mark.asyncio
    async def test_invalid_trace_id_header(
        self, middleware, mock_request, mock_call_next
    ):
        """Test handling of invalid trace_id in headers."""

        with patch.object(middleware, "_logger") as mock_logger:
            mock_bound_logger = Mock()
            mock_logger.bind.return_value = mock_bound_logger

            # Set invalid trace_id
            mock_request.headers = {"x-trace-id": "invalid-uuid-format"}

            response = await middleware.dispatch(mock_request, mock_call_next)

            # Verify a new valid UUID is generated
            trace_id = response.headers["X-Trace-ID"]
            assert uuid.UUID(trace_id)  # Should not raise ValueError
            assert trace_id != "invalid-uuid-format"

    @pytest.mark.asyncio
    async def test_multiple_trace_header_variations(
        self, middleware, mock_request, mock_call_next
    ):
        """Test that various trace header formats are recognized."""

        test_cases = ["x-trace-id", "trace-id", "x-correlation-id", "correlation-id"]

        with patch.object(middleware, "_logger") as mock_logger:
            mock_bound_logger = Mock()
            mock_logger.bind.return_value = mock_bound_logger

            for header_key in test_cases:
                trace_id = str(uuid.uuid4())
                mock_request.headers = {header_key: trace_id}

                response = await middleware.dispatch(mock_request, mock_call_next)

                assert response.headers["X-Trace-ID"] == trace_id

    @pytest.mark.asyncio
    async def test_authentication_exception_handling(
        self, middleware, mock_request, mock_response
    ):
        """Test handling of AuthenticationException."""

        auth_exception = AuthenticationException("Invalid credentials")

        async def failing_call_next(request: Request):  # noqa: ARG001
            raise auth_exception

        with patch.object(middleware, "_logger") as mock_logger:
            mock_bound_logger = Mock()
            mock_logger.bind.return_value = mock_bound_logger

            with patch(
                "app.api.middlewares.request_middleware.EXCEPTION_HANDLERS"
            ) as mock_handlers:
                mock_handler = AsyncMock(return_value=mock_response)
                mock_handlers.__getitem__.return_value = mock_handler
                mock_handlers.items.return_value = [
                    (AuthenticationException, mock_handler)
                ]

                await middleware.dispatch(mock_request, failing_call_next)

                # Verify exception handler was called
                mock_handler.assert_called_once_with(mock_request, auth_exception)

                # Verify trace information is added to exception
                assert auth_exception.trace_id is not None
                assert auth_exception.request_id is not None

    @pytest.mark.asyncio
    async def test_validation_exception_handling(
        self, middleware, mock_request, mock_response
    ):
        """Test handling of ValidationException."""

        validation_exception = ValidationException("Invalid input data")

        async def failing_call_next(request):  # noqa: ARG001
            raise validation_exception

        with patch.object(middleware, "_logger") as mock_logger:
            mock_bound_logger = Mock()
            mock_logger.bind.return_value = mock_bound_logger

            with patch(
                "app.api.middlewares.request_middleware.EXCEPTION_HANDLERS"
            ) as mock_handlers:
                mock_handler = AsyncMock(return_value=mock_response)
                mock_handlers.__getitem__.return_value = mock_handler
                mock_handlers.items.return_value = [(ValidationException, mock_handler)]

                await middleware.dispatch(mock_request, failing_call_next)

                # Verify exception handler was called
                mock_handler.assert_called_once_with(mock_request, validation_exception)

    @pytest.mark.asyncio
    async def test_generic_exception_handling(
        self, middleware, mock_request, mock_response
    ):
        """Test handling of unexpected exceptions."""

        generic_exception = ValueError("Unexpected error")

        async def failing_call_next(request):  # noqa: ARG001
            raise generic_exception

        with patch.object(middleware, "_logger") as mock_logger:
            mock_bound_logger = Mock()
            mock_logger.bind.return_value = mock_bound_logger

            with patch(
                "app.api.middlewares.request_middleware.EXCEPTION_HANDLERS"
            ) as mock_handlers:
                fallback_handler = AsyncMock(return_value=mock_response)
                mock_handlers.__getitem__.return_value = fallback_handler
                mock_handlers.items.return_value = []  # No specific handler found
                mock_handlers.__getitem__.side_effect = (
                    lambda key: fallback_handler if key is Exception else None
                )

                await middleware.dispatch(mock_request, failing_call_next)

                # Verify fallback handler was called
                fallback_handler.assert_called_once_with(
                    mock_request, generic_exception
                )

    @pytest.mark.asyncio
    async def test_performance_timing(self, middleware, mock_request, mock_response):
        """Test that performance timing is accurately measured."""

        # Add delay to call_next
        async def delayed_call_next(request):  # noqa: ARG001
            await asyncio.sleep(0.1)  # 100ms delay
            return mock_response

        with patch.object(middleware, "_logger") as mock_logger:
            mock_bound_logger = Mock()
            mock_logger.bind.return_value = mock_bound_logger

            start_time = time.time()
            response = await middleware.dispatch(mock_request, delayed_call_next)
            end_time = time.time()

            # Verify response time header exists and is reasonable
            response_time = float(response.headers["X-Response-Time"].rstrip("s"))
            actual_duration = end_time - start_time

            # Should be close to actual duration (within 10ms tolerance)
            assert abs(response_time - actual_duration) < 0.01

    @pytest.mark.asyncio
    async def test_request_context_logging(
        self, middleware, mock_request_with_trace, mock_call_next
    ):
        """Test that comprehensive request context is logged."""

        with patch.object(middleware, "_logger") as mock_logger:
            mock_bound_logger = Mock()
            mock_logger.bind.return_value = mock_bound_logger

            await middleware.dispatch(mock_request_with_trace, mock_call_next)

            # Verify logger.bind was called with comprehensive context
            bind_calls = mock_logger.bind.call_args_list
            assert len(bind_calls) >= 2  # At least request start and completion

            # Check request start logging
            start_context = bind_calls[0][1]  # kwargs from first bind call
            assert "trace_id" in start_context
            assert "request_id" in start_context
            assert "client_ip" in start_context
            assert "method" in start_context
            assert "url" in start_context

    @pytest.mark.asyncio
    async def test_response_size_logging(self, middleware, mock_request):
        """Test that response size is logged when available."""

        mock_response = Mock(spec=Response)
        mock_response.status_code = 200
        mock_response.headers = {"content-length": "1024"}

        async def sized_call_next(request):  # noqa: ARG001
            return mock_response

        with patch.object(middleware, "_logger") as mock_logger:
            mock_bound_logger = Mock()
            mock_logger.bind.return_value = mock_bound_logger

            await middleware.dispatch(mock_request, sized_call_next)

            # Verify response context includes size
            bind_calls = mock_logger.bind.call_args_list
            response_context = bind_calls[1][1]  # Second bind call for response
            assert "response_size" in response_context

    @pytest.mark.asyncio
    async def test_cache_status_logging(self, middleware, mock_request):
        """Test that cache status is logged when available."""

        mock_response = Mock(spec=Response)
        mock_response.status_code = 200
        mock_response.headers = {"cache-control": "max-age=3600"}

        async def cached_call_next(request):  # noqa: ARG001
            return mock_response

        with patch.object(middleware, "_logger") as mock_logger:
            mock_bound_logger = Mock()
            mock_logger.bind.return_value = mock_bound_logger

            await middleware.dispatch(mock_request, cached_call_next)

            # Verify cache status is logged
            bind_calls = mock_logger.bind.call_args_list
            response_context = bind_calls[1][1]
            assert "cache_status" in response_context

    @pytest.mark.asyncio
    async def test_traceback_logging_on_exception(
        self, middleware, mock_request, mock_response
    ):
        """Test that full traceback is logged for exceptions."""

        def create_nested_exception():
            try:
                msg = "Original error"
                raise ValueError(msg)
            except ValueError as e:
                msg = "Nested error"
                raise RuntimeError(msg) from e

        async def failing_call_next(request):  # noqa: ARG001
            create_nested_exception()

        with patch(
            "app.api.middlewares.request_middleware.EXCEPTION_HANDLERS"
        ) as mock_handlers:
            fallback_handler = AsyncMock(return_value=mock_response)
            mock_handlers.items.return_value = []
            mock_handlers.__getitem__.return_value = fallback_handler

            with patch.object(middleware, "_logger") as mock_logger:
                mock_bound_logger = Mock()
                mock_logger.bind.return_value = mock_bound_logger

                await middleware.dispatch(mock_request, failing_call_next)

                # Verify error context includes traceback
                error_bind_call = mock_logger.bind.call_args_list[-1]
                error_context = error_bind_call[1]
                assert "traceback" in error_context
                assert "exception_type" in error_context
                assert "exception_message" in error_context

    @pytest.mark.asyncio
    async def test_app_exception_preserves_trace_info(
        self, middleware, mock_request, mock_response
    ):
        """Test that AppException trace info is preserved/set correctly."""

        app_exception = AppException(
            error_code=ErrorCode.VALIDATION_ERROR, message="Test error"
        )

        async def failing_call_next(request):  # noqa: ARG001
            raise app_exception

        with patch.object(middleware, "_logger") as mock_logger:
            mock_bound_logger = Mock()
            mock_logger.bind.return_value = mock_bound_logger

            with patch(
                "app.api.middlewares.request_middleware.EXCEPTION_HANDLERS"
            ) as mock_handlers:
                mock_handler = AsyncMock(return_value=mock_response)
                mock_handlers.items.return_value = [(AppException, mock_handler)]

                await middleware.dispatch(mock_request, failing_call_next)

                # Verify trace info was set on exception
                assert app_exception.trace_id == mock_request.state.trace_id
                assert app_exception.request_id == mock_request.state.request_id

    @pytest.mark.asyncio
    async def test_unknown_client_ip_handling(self, middleware, mock_call_next):
        """Test handling when client IP is unknown."""

        mock_request = Mock()
        mock_request.client = None
        mock_request.method = "GET"
        mock_request.url.path = "/test"
        mock_request.url = Mock()
        mock_request.query_params = {}
        mock_request.headers = {}
        mock_request.state = Mock()

        with patch.object(middleware, "_logger") as mock_logger:
            mock_bound_logger = Mock()
            mock_logger.bind.return_value = mock_bound_logger

            await middleware.dispatch(mock_request, mock_call_next)

            # Verify "unknown" is used for client IP
            bind_calls = mock_logger.bind.call_args_list
            start_context = bind_calls[0][1]
            assert start_context["client_ip"] == "unknown"
