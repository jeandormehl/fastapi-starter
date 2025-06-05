from unittest.mock import AsyncMock, Mock, patch

import pytest
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from app.common.middlewares.logging_middleware import LoggingMiddleware


class TestLoggingMiddleware:
    """Comprehensive test suite for LoggingMiddleware."""

    @pytest.fixture
    def mock_app(self):
        """Create a mock ASGI application."""

        return Mock(spec=ASGIApp)

    @pytest.fixture
    def middleware(self, mock_app):
        """Create LoggingMiddleware instance for testing."""

        return LoggingMiddleware(mock_app)

    @pytest.fixture
    def mock_call_next(self):
        """Mock call_next function for middleware testing."""

        return AsyncMock()

    @pytest.fixture
    def sample_response(self):
        """Create a sample response for testing."""

        response = JSONResponse({"message": "success"}, status_code=200)
        response.headers["content-length"] = "25"
        response.headers["cache-control"] = "no-cache"
        return response

    @pytest.mark.asyncio
    async def test_dispatch_successful_request(
        self, middleware, mock_request, mock_call_next, sample_response
    ):
        """Test successful request logging flow."""

        mock_call_next.return_value = sample_response

        with (
            patch("time.time", side_effect=[1000.0, 1002.5]),
            patch.object(middleware._logger, "bind") as mock_bind,
        ):
            mock_logger = Mock()
            mock_bind.return_value = mock_logger

            result = await middleware.dispatch(mock_request, mock_call_next)

            # Verify request start time was stored
            assert hasattr(mock_request.state, "start_time")
            assert mock_request.state.start_time == 1000.0

            # Verify logging was called twice (start and completion)
            assert mock_bind.call_count == 2

            # Verify response headers
            assert result.headers["X-Response-Time"] == "2.500s"
            assert result == sample_response

            # Verify success logging
            mock_logger.info.assert_called()

    @pytest.mark.asyncio
    async def test_request_context_creation(
        self, middleware, mock_request, mock_call_next, sample_response
    ):
        """Test comprehensive request context creation."""

        # Setup detailed request mock
        mock_request.method = "POST"
        mock_request.url = Mock()
        mock_request.url.__str__ = Mock(
            return_value="https://api.example.com/api/users?param=value"
        )
        mock_request.url.path = "/api/users"
        mock_request.query_params = {"param": "value", "page": "1"}
        mock_request.headers = {
            "user-agent": "Mozilla/5.0 Test Browser",
            "content-type": "application/json",
            "content-length": "150",
            "authorization": "Bearer token123",
        }
        mock_request.client.host = "203.0.113.42"

        mock_call_next.return_value = sample_response

        with (
            patch("time.time", side_effect=[1000.0, 1001.0]),
            patch.object(middleware._logger, "bind") as mock_bind,
        ):
            mock_logger = Mock()
            mock_bind.return_value = mock_logger

            await middleware.dispatch(mock_request, mock_call_next)

            # Verify request context (first call)
            request_context = mock_bind.call_args_list[0][1]

            assert request_context["trace_id"] == "test-trace-id-12345"
            assert request_context["request_id"] == "test-request-id-67890"
            assert request_context["client_ip"] == "203.0.113.42"
            assert request_context["method"] == "POST"
            assert (
                request_context["url"]
                == "https://api.example.com/api/users?param=value"
            )
            assert request_context["path"] == "/api/users"
            assert "{'param': 'value', 'page': '1'}" in request_context["query_params"]
            assert request_context["user_agent"] == "Mozilla/5.0 Test Browser"
            assert request_context["content_type"] == "application/json"
            assert request_context["content_length"] == "150"
            assert request_context["event"] == "request_started"

    @pytest.mark.asyncio
    async def test_response_context_creation(
        self, middleware, mock_request, mock_call_next, sample_response
    ):
        """Test comprehensive response context creation."""

        mock_call_next.return_value = sample_response

        with (
            patch("time.time", side_effect=[1000.0, 1003.2]),
            patch.object(middleware._logger, "bind") as mock_bind,
        ):
            mock_logger = Mock()
            mock_bind.return_value = mock_logger

            await middleware.dispatch(mock_request, mock_call_next)

            # Verify response context (second call)
            response_context = mock_bind.call_args_list[1][1]

            assert response_context["trace_id"] == "test-trace-id-12345"
            assert response_context["request_id"] == "test-request-id-67890"
            assert response_context["status_code"] == 200
            assert response_context["duration_ms"] == 3200.0
            assert response_context["response_size"] == "25"
            assert response_context["cache_status"] == "no-cache"
            assert response_context["event"] == "request_completed"

    @pytest.mark.asyncio
    async def test_request_without_query_params(
        self, middleware, mock_request, mock_call_next, sample_response
    ):
        """Test request context when query params are empty."""

        mock_request.query_params = {}
        mock_call_next.return_value = sample_response

        with (
            patch("time.time", side_effect=[1000.0, 1001.0]),
            patch.object(middleware._logger, "bind") as mock_bind,
        ):
            mock_logger = Mock()
            mock_bind.return_value = mock_logger

            await middleware.dispatch(mock_request, mock_call_next)

            request_context = mock_bind.call_args_list[0][1]
            assert request_context["query_params"] is None

    @pytest.mark.asyncio
    async def test_request_without_client(
        self, middleware, mock_request, mock_call_next, sample_response
    ):
        """Test request context when client information is missing."""

        mock_request.client = None
        mock_call_next.return_value = sample_response

        with (
            patch("time.time", side_effect=[1000.0, 1001.0]),
            patch.object(middleware._logger, "bind") as mock_bind,
        ):
            mock_logger = Mock()
            mock_bind.return_value = mock_logger

            await middleware.dispatch(mock_request, mock_call_next)

            request_context = mock_bind.call_args_list[0][1]
            assert request_context["client_ip"] == "unknown"

    @pytest.mark.asyncio
    async def test_missing_trace_context(
        self, middleware, mock_request, mock_call_next, sample_response
    ):
        """Test logging when trace context is missing."""

        # Remove trace context
        del mock_request.state.trace_id
        del mock_request.state.request_id

        mock_call_next.return_value = sample_response

        with (
            patch("time.time", side_effect=[1000.0, 1001.0]),
            patch.object(middleware._logger, "bind") as mock_bind,
        ):
            mock_logger = Mock()
            mock_bind.return_value = mock_logger

            await middleware.dispatch(mock_request, mock_call_next)

            # Verify unknown values are used
            request_context = mock_bind.call_args_list[0][1]
            assert request_context["trace_id"] == "unknown"
            assert request_context["request_id"] == "unknown"

    @pytest.mark.asyncio
    async def test_response_header_variations(
        self, middleware, mock_request, mock_call_next
    ):
        """Test response context with different header combinations."""

        # Test response without optional headers
        response_no_headers = JSONResponse({"message": "success"}, status_code=201)
        mock_call_next.return_value = response_no_headers

        with (
            patch("time.time", side_effect=[1000.0, 1001.0]),
            patch.object(middleware._logger, "bind") as mock_bind,
        ):
            mock_logger = Mock()
            mock_bind.return_value = mock_logger

            await middleware.dispatch(mock_request, mock_call_next)

            response_context = mock_bind.call_args_list[1][1]
            assert response_context["response_size"] == "21"
            assert response_context["cache_status"] is None
            assert response_context["status_code"] == 201

    @pytest.mark.asyncio
    async def test_performance_header_precision(
        self, middleware, mock_request, mock_call_next, sample_response
    ):
        """Test precision of performance timing header."""

        mock_call_next.return_value = sample_response

        # Test various durations for precision
        test_durations = [0.001, 0.123, 1.456789, 10.0]

        for duration in test_durations:
            with (
                patch("time.time", side_effect=[1000.0, 1000.0 + duration]),
                patch.object(middleware._logger, "bind") as mock_bind,
            ):
                mock_logger = Mock()
                mock_bind.return_value = mock_logger

                result = await middleware.dispatch(mock_request, mock_call_next)

                expected_header = f"{duration:.3f}s"
                assert result.headers["X-Response-Time"] == expected_header

    @pytest.mark.asyncio
    async def test_logging_calls_sequence(
        self, middleware, mock_request, mock_call_next, sample_response
    ):
        """Test the sequence and content of logging calls."""

        mock_call_next.return_value = sample_response

        with (
            patch("time.time", side_effect=[1000.0, 1002.0]),
            patch.object(middleware._logger, "bind") as mock_bind,
        ):
            mock_logger = Mock()
            mock_bind.return_value = mock_logger

            await middleware.dispatch(mock_request, mock_call_next)

            # Verify two bind calls were made
            assert mock_bind.call_count == 2

            # Verify two info calls were made (request start and completion)
            assert mock_logger.info.call_count == 2

            # Verify call messages
            info_calls = mock_logger.info.call_args_list
            assert info_calls[0][0][0] == "request started"
            assert info_calls[1][0][0] == "request completed successfully"

    @pytest.mark.asyncio
    async def test_request_state_persistence(
        self, middleware, mock_request, mock_call_next, sample_response
    ):
        """Test that request state is properly maintained."""

        initial_state_attrs = set(dir(mock_request.state))
        start_time = 1000.0

        mock_call_next.return_value = sample_response

        with (
            patch("time.time", return_value=start_time),
            patch.object(middleware._logger, "bind") as mock_bind,
        ):
            mock_logger = Mock()
            mock_bind.return_value = mock_logger

            await middleware.dispatch(mock_request, mock_call_next)

            # Verify start_time was added to request state
            assert hasattr(mock_request.state, "start_time")
            assert mock_request.state.start_time == start_time

            # Verify other state attributes weren't modified
            final_state_attrs = set(dir(mock_request.state))
            new_attrs = final_state_attrs - initial_state_attrs
            assert "start_time" in new_attrs

    @pytest.mark.asyncio
    async def test_comprehensive_header_logging(
        self, middleware, mock_request, mock_call_next, sample_response
    ):
        """Test logging of various request headers."""

        # Setup comprehensive headers
        mock_request.headers = {
            "user-agent": "Custom-Agent/1.0",
            "content-type": "application/xml",
            "content-length": "500",
            "accept": "application/json",
            "authorization": "Bearer secret-token",
            "x-forwarded-for": "192.168.1.1",
            "referer": "https://example.com/previous",
            "accept-language": "en-US,en;q=0.9",
        }

        mock_call_next.return_value = sample_response

        with (
            patch("time.time", side_effect=[1000.0, 1001.0]),
            patch.object(middleware._logger, "bind") as mock_bind,
        ):
            mock_logger = Mock()
            mock_bind.return_value = mock_logger

            await middleware.dispatch(mock_request, mock_call_next)

            request_context = mock_bind.call_args_list[0][1]

            # Verify specific headers are logged
            assert request_context["user_agent"] == "Custom-Agent/1.0"
            assert request_context["content_type"] == "application/xml"
            assert request_context["content_length"] == "500"

    @pytest.mark.asyncio
    async def test_edge_case_empty_headers(
        self, middleware, mock_request, mock_call_next, sample_response
    ):
        """Test handling of missing headers."""

        # Remove optional headers
        mock_request.headers = {}

        mock_call_next.return_value = sample_response

        with (
            patch("time.time", side_effect=[1000.0, 1001.0]),
            patch.object(middleware._logger, "bind") as mock_bind,
        ):
            mock_logger = Mock()
            mock_bind.return_value = mock_logger

            await middleware.dispatch(mock_request, mock_call_next)

            request_context = mock_bind.call_args_list[0][1]

            # Verify None values for missing headers
            assert request_context["user_agent"] is None
            assert request_context["content_type"] is None
            assert request_context["content_length"] is None

    @pytest.mark.asyncio
    async def test_duration_calculation_accuracy(
        self, middleware, mock_request, mock_call_next, sample_response
    ):
        """Test accurate duration calculation across various scenarios."""

        mock_call_next.return_value = sample_response

        # Test various timing scenarios
        timing_scenarios = [
            (1000.0, 1000.1),  # 100ms
            (1000.0, 1001.0),  # 1 second
            (1000.0, 1005.5),  # 5.5 seconds
            (1000.0, 1000.001),  # 1ms
        ]

        for start_time, end_time in timing_scenarios:
            expected_duration_ms = round((end_time - start_time) * 1000, 2)

            with (
                patch("time.time", side_effect=[start_time, end_time]),
                patch.object(middleware._logger, "bind") as mock_bind,
            ):
                mock_logger = Mock()
                mock_bind.return_value = mock_logger

                await middleware.dispatch(mock_request, mock_call_next)

                response_context = mock_bind.call_args_list[1][1]
                assert response_context["duration_ms"] == expected_duration_ms
