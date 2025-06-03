import signal
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from pytest_httpx import HTTPXMock

from app.core.config import Configuration
from app.core.logging.parseable_sink import ParseableSink


@pytest.fixture
def mock_config():
    """Create a mock configuration for testing."""
    config = Mock(spec=Configuration)
    config.parseable_url = "https://test-parseable.com"
    config.parseable_stream = "test-stream"
    config.parseable_username = "test-user"
    config.parseable_password = Mock()
    config.parseable_password.get_secret_value.return_value = "test-password"
    config.parseable_batch_size = 10
    config.parseable_flush_interval = 1.0
    config.parseable_max_retries = 2
    config.parseable_retry_delay = 0.1
    return config


@pytest.fixture
def mock_loguru_record():
    """Create a mock loguru record for testing."""
    record = {
        "time": Mock(),
        "level": Mock(),
        "name": "test.logger",
        "function": "test_function",
        "line": 42,
        "message": "Test log message",
        "module": "test_module",
        "file": Mock(),
        "process": Mock(),
        "thread": Mock(),
        "extra": {},
    }

    # Configure mocks
    record["time"].isoformat.return_value = "2023-01-01T12:00:00Z"
    record["level"].name = "INFO"
    record["file"].name = "test_file.py"
    record["process"].id = 12345
    record["thread"].id = 67890
    record["thread"].name = "MainThread"

    return record


# noinspection PyUnusedLocal
class TestParseableSinkInitialization:
    """Test ParseableSink initialization and configuration."""

    @patch("app.core.logging.parseable_sink.atexit.register")
    @patch("app.core.logging.parseable_sink.signal.signal")
    @patch("app.core.logging.parseable_sink.Thread")
    def test_init_sets_configuration_correctly(
        self,
        mock_thread,  # noqa: ARG002
        mock_signal,
        mock_atexit,
        mock_config,
    ):
        """Test that initialization sets all configuration values correctly."""

        sink = ParseableSink(mock_config)

        assert sink.config == mock_config
        assert sink.base_url == "https://test-parseable.com"
        assert sink.stream_name == "test-stream"
        assert sink.username == "test-user"
        assert sink.password == "test-password"
        assert sink.batch_size == 10
        assert sink.flush_interval == 1.0
        assert sink.max_retries == 2
        assert sink.retry_delay == 0.1

        # Verify signal handlers are registered
        mock_signal.assert_any_call(signal.SIGTERM, sink._signal_handler)
        mock_signal.assert_any_call(signal.SIGINT, sink._signal_handler)
        mock_atexit.assert_called_once_with(sink.cleanup)

    @patch("app.core.logging.parseable_sink.atexit.register")
    @patch("app.core.logging.parseable_sink.signal.signal")
    @patch("app.core.logging.parseable_sink.Thread")
    def test_init_with_default_values(self, mock_thread, mock_signal, mock_atexit):  # noqa: ARG002
        """Test initialization with default configuration values."""

        config = Mock(spec=Configuration)
        config.parseable_url = "https://default.com"
        config.parseable_stream = "default-stream"
        config.parseable_username = "default-user"
        config.parseable_password = Mock()
        config.parseable_password.get_secret_value.return_value = "default-password"

        sink = ParseableSink(config)

        # Check default values are set
        assert sink.batch_size == 100  # Default from getattr
        assert sink.flush_interval == 5.0  # Default from getattr
        assert sink.max_retries == 3  # Default from getattr
        assert sink.retry_delay == 1.0  # Default from getattr

    @patch("app.core.logging.parseable_sink.atexit.register")
    @patch("app.core.logging.parseable_sink.signal.signal")
    @patch("app.core.logging.parseable_sink.Thread")
    def test_init_starts_background_thread(
        self,
        mock_thread,
        mock_signal,  # noqa: ARG002
        mock_atexit,  # noqa: ARG002
        mock_config,
    ):
        """Test that initialization starts the background processing thread."""

        ParseableSink(mock_config)

        mock_thread.assert_called_once()
        thread_call = mock_thread.call_args
        assert thread_call[1]["daemon"] is True

        # Verify thread.start() was called
        mock_thread.return_value.start.assert_called_once()


# noinspection PyUnusedLocal
class TestLogProcessing:
    """Test log message processing and serialization."""

    @patch("app.core.logging.parseable_sink.atexit.register")
    @patch("app.core.logging.parseable_sink.signal.signal")
    @patch("app.core.logging.parseable_sink.Thread")
    def test_log_processes_basic_record(
        self,
        mock_thread,  # noqa: ARG002
        mock_signal,  # noqa: ARG002
        mock_atexit,  # noqa: ARG002
        mock_config,
        mock_loguru_record,
    ):
        """Test basic log record processing."""
        sink = ParseableSink(mock_config)

        # Create a mock message object
        message = Mock()
        message.record = mock_loguru_record

        sink.log(message)

        # Verify log entry was added to buffer
        assert len(sink._buffer) == 1
        log_entry = sink._buffer[0]

        assert log_entry["timestamp"] == "2023-01-01T12:00:00Z"
        assert log_entry["level"] == "INFO"
        assert log_entry["logger"] == "test.logger"
        assert log_entry["function"] == "test_function"
        assert log_entry["line"] == 42
        assert log_entry["message"] == "Test log message"
        assert log_entry["module"] == "test_module"
        assert log_entry["file"] == "test_file.py"
        assert log_entry["process_id"] == 12345
        assert log_entry["thread_id"] == 67890
        assert log_entry["thread_name"] == "MainThread"

    @patch("app.core.logging.parseable_sink.atexit.register")
    @patch("app.core.logging.parseable_sink.signal.signal")
    @patch("app.core.logging.parseable_sink.Thread")
    def test_log_handles_extra_data(
        self,
        mock_thread,  # noqa: ARG002
        mock_signal,  # noqa: ARG002
        mock_atexit,  # noqa: ARG002
        mock_config,
        mock_loguru_record,
    ):
        """Test log processing with extra data."""
        sink = ParseableSink(mock_config)

        # Add extra data to record
        mock_loguru_record["extra"] = {
            "user_id": 123,
            "request_id": "abc-123",
            "custom_data": {"nested": "value"},
        }

        message = Mock()
        message.record = mock_loguru_record

        sink.log(message)

        log_entry = sink._buffer[0]
        assert log_entry["user_id"] == 123
        assert log_entry["request_id"] == "abc-123"
        assert log_entry["custom_data"] == {"nested": "value"}

    @patch("app.core.logging.parseable_sink.atexit.register")
    @patch("app.core.logging.parseable_sink.signal.signal")
    @patch("app.core.logging.parseable_sink.Thread")
    def test_log_handles_exception_info(
        self,
        mock_thread,  # noqa: ARG002
        mock_signal,  # noqa: ARG002
        mock_atexit,  # noqa: ARG002
        mock_config,
        mock_loguru_record,
    ):
        """Test log processing with exception information."""
        sink = ParseableSink(mock_config)

        # Create mock exception info
        exc_type = ValueError
        exc_value = ValueError("Test error")
        exc_traceback = Mock()
        exc_info = (exc_type, exc_value, exc_traceback)

        mock_loguru_record["extra"] = {"exc_info": exc_info}

        message = Mock()
        message.record = mock_loguru_record

        with patch("traceback.format_exception") as mock_format:
            mock_format.return_value = ["Traceback line 1", "Traceback line 2"]
            sink.log(message)

        log_entry = sink._buffer[0]
        assert "exception_type" in log_entry
        assert "exception_message" in log_entry
        assert log_entry["exception_traceback"] == [
            "Traceback line 1",
            "Traceback line 2",
        ]

    @patch("app.core.logging.parseable_sink.atexit.register")
    @patch("app.core.logging.parseable_sink.signal.signal")
    @patch("app.core.logging.parseable_sink.Thread")
    def test_log_handles_non_serializable_objects(
        self,
        mock_thread,  # noqa: ARG002
        mock_signal,  # noqa: ARG002
        mock_atexit,  # noqa: ARG002
        mock_config,
        mock_loguru_record,
    ):
        """Test log processing with non-JSON-serializable objects."""
        sink = ParseableSink(mock_config)

        # Create non-serializable object
        class NonSerializable:
            def __str__(self):
                return "non_serializable_object"

        mock_loguru_record["extra"] = {
            "serializable": "value",
            "non_serializable": NonSerializable(),
        }

        message = Mock()
        message.record = mock_loguru_record

        sink.log(message)

        log_entry = sink._buffer[0]
        assert log_entry["serializable"] == "value"
        assert log_entry["non_serializable"] == "non_serializable_object"

    @patch("app.core.logging.parseable_sink.atexit.register")
    @patch("app.core.logging.parseable_sink.signal.signal")
    @patch("app.core.logging.parseable_sink.Thread")
    @patch("builtins.print")
    def test_log_handles_processing_errors(
        self,
        mock_print,
        mock_thread,  # noqa: ARG002
        mock_signal,  # noqa: ARG002
        mock_atexit,  # noqa: ARG002
        mock_config,
    ):
        """Test log processing error handling."""
        sink = ParseableSink(mock_config)

        # Create a message that will cause an error
        message = Mock()
        message.record = None  # This should cause an error

        sink.log(message)

        # Verify error was printed to stderr
        mock_print.assert_called()


class TestHTTPCommunication:
    """Test HTTP communication with Parseable service."""

    @pytest.mark.asyncio
    async def test_send_batch_success(self, mock_config, httpx_mock: HTTPXMock):
        """Test successful batch sending."""
        with (
            patch("app.core.logging.parseable_sink.atexit.register"),
            patch("app.core.logging.parseable_sink.signal.signal"),
            patch("app.core.logging.parseable_sink.Thread"),
        ):
            sink = ParseableSink(mock_config)
            sink._client = httpx.AsyncClient()

            # Mock successful response
            httpx_mock.add_response(
                url="https://test-parseable.com/api/v1/ingest",
                method="POST",
                status_code=200,
            )

            batch = [{"test": "log1"}, {"test": "log2"}]

            # Should not raise any exception
            await sink._send_batch(batch)

            # Verify request was made correctly
            request = httpx_mock.get_request()
            assert request.method == "POST"
            assert request.url.path == "/api/v1/ingest"
            assert request.headers["Content-Type"] == "application/json"
            assert request.headers["X-P-Stream"] == "test-stream"
            assert request.headers["User-Agent"] == "fastapi-starter-parseable-sink/1.0"

    @pytest.mark.asyncio
    async def test_send_batch_with_auth(self, mock_config, httpx_mock: HTTPXMock):
        """Test batch sending with authentication."""
        with (
            patch("app.core.logging.parseable_sink.atexit.register"),
            patch("app.core.logging.parseable_sink.signal.signal"),
            patch("app.core.logging.parseable_sink.Thread"),
        ):
            sink = ParseableSink(mock_config)
            sink._client = httpx.AsyncClient()

            httpx_mock.add_response(
                url="https://test-parseable.com/api/v1/ingest",
                method="POST",
                status_code=200,
            )

            batch = [{"test": "log1"}]
            await sink._send_batch(batch)

            # Verify authentication was included
            request = httpx_mock.get_request()
            assert "Authorization" in request.headers

    @pytest.mark.asyncio
    async def test_send_batch_http_error(self, mock_config, httpx_mock: HTTPXMock):
        """Test batch sending with HTTP error response."""
        with (
            patch("app.core.logging.parseable_sink.atexit.register"),
            patch("app.core.logging.parseable_sink.signal.signal"),
            patch("app.core.logging.parseable_sink.Thread"),
            patch("builtins.print") as mock_print,
        ):
            sink = ParseableSink(mock_config)
            sink._client = httpx.AsyncClient()

            httpx_mock.add_response(
                url="https://test-parseable.com/api/v1/ingest",
                method="POST",
                status_code=500,
                text="Internal Server Error",
            )

            batch = [{"test": "log1"}]

            with pytest.raises(httpx.HTTPStatusError):
                await sink._send_batch(batch)

            # Verify error was logged
            mock_print.assert_called()
            assert "HTTP error 500" in str(mock_print.call_args)

    @pytest.mark.asyncio
    async def test_send_batch_request_error(self, mock_config):
        """Test batch sending with request error."""
        with (
            patch("app.core.logging.parseable_sink.atexit.register"),
            patch("app.core.logging.parseable_sink.signal.signal"),
            patch("app.core.logging.parseable_sink.Thread"),
            patch("builtins.print") as mock_print,
        ):
            sink = ParseableSink(mock_config)

            # Create a client that will raise a connection error
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.RequestError("Connection failed")
            sink._client = mock_client

            batch = [{"test": "log1"}]

            with pytest.raises(httpx.RequestError):
                await sink._send_batch(batch)

            # Verify error was logged
            mock_print.assert_called()
            assert "Request error" in str(mock_print.call_args)

    @pytest.mark.asyncio
    async def test_send_batch_without_client(self, mock_config):
        """Test send_batch raises error when client is not initialized."""
        with (
            patch("app.core.logging.parseable_sink.atexit.register"),
            patch("app.core.logging.parseable_sink.signal.signal"),
            patch("app.core.logging.parseable_sink.Thread"),
        ):
            sink = ParseableSink(mock_config)
            sink._client = None

            batch = [{"test": "log1"}]

            with pytest.raises(RuntimeError, match="http client not initialized"):
                await sink._send_batch(batch)


# noinspection PyUnusedLocal
class TestRetryLogic:
    """Test retry logic and error handling."""

    @pytest.mark.asyncio
    async def test_flush_buffer_retry_on_failure(self, mock_config):
        """Test retry logic when send_batch fails."""
        with (
            patch("app.core.logging.parseable_sink.atexit.register"),
            patch("app.core.logging.parseable_sink.signal.signal"),
            patch("app.core.logging.parseable_sink.Thread"),
            patch("builtins.print") as mock_print,  # noqa: F841
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_config.parseable_max_retries = 2
            mock_config.parseable_retry_delay = 0.1

            sink = ParseableSink(mock_config)
            sink._buffer.extend([{"test": "entry1"}])

            # Mock _send_batch to fail twice, then succeed
            call_count = 0

            async def mock_send_batch(batch):  # noqa: ARG001
                nonlocal call_count
                call_count += 1
                if call_count <= 2:
                    msg = "Connection failed"
                    raise httpx.RequestError(msg)
                # Third call succeeds (no exception)

            with patch.object(sink, "_send_batch", side_effect=mock_send_batch):
                await sink._flush_buffer()

            # Verify retries occurred with exponential backoff
            assert mock_sleep.call_count == 2
            mock_sleep.assert_any_call(0.1 * (2**0))  # First retry
            mock_sleep.assert_any_call(0.1 * (2**1))  # Second retry


class TestBackgroundProcessing:
    """Test background processing functionality."""

    @pytest.mark.asyncio
    async def test_background_processor_creates_client(self, mock_config):
        """Test that background processor creates HTTP client."""
        with (
            patch("app.core.logging.parseable_sink.atexit.register"),
            patch("app.core.logging.parseable_sink.signal.signal"),
            patch("app.core.logging.parseable_sink.Thread"),
        ):
            sink = ParseableSink(mock_config)
            sink._running = False  # Stop immediately to avoid infinite loop

            await sink._background_processor()

            # Client should be created and closed
            assert sink._client is not None

    @pytest.mark.asyncio
    async def test_background_processor_flushes_periodically(self, mock_config):
        """Test that background processor flushes buffer periodically."""
        with (
            patch("app.core.logging.parseable_sink.atexit.register"),
            patch("app.core.logging.parseable_sink.signal.signal"),
            patch("app.core.logging.parseable_sink.Thread"),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_config.parseable_flush_interval = 0.1

            sink = ParseableSink(mock_config)

            # Add some data to buffer
            sink._buffer.extend([{"test": "entry1"}])

            # Mock _flush_buffer to track calls
            flush_calls = 0

            async def mock_flush():
                nonlocal flush_calls
                flush_calls += 1
                if flush_calls >= 2:
                    sink._running = False  # Stop after 2 flushes

            with patch.object(sink, "_flush_buffer", side_effect=mock_flush):
                await sink._background_processor()

            # Verify sleep was called with correct interval
            assert mock_sleep.call_count >= 2
            mock_sleep.assert_called_with(0.1)

            # Verify flush was called
            assert flush_calls >= 2

    @pytest.mark.asyncio
    async def test_background_processor_handles_exceptions(self, mock_config):
        """Test that background processor handles exceptions gracefully."""
        with (
            patch("app.core.logging.parseable_sink.atexit.register"),
            patch("app.core.logging.parseable_sink.signal.signal"),
            patch("app.core.logging.parseable_sink.Thread"),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            sink = ParseableSink(mock_config)
            sink._running = False  # Stop immediately

            # Mock _flush_buffer to raise an exception
            with patch.object(
                sink, "_flush_buffer", side_effect=Exception("Test error")
            ):
                # Should not raise exception
                await sink._background_processor()


# noinspection PyUnusedLocal
class TestThreadSafety:
    """Test thread safety of ParseableSink operations."""

    @patch("app.core.logging.parseable_sink.atexit.register")
    @patch("app.core.logging.parseable_sink.signal.signal")
    @patch("app.core.logging.parseable_sink.Thread")
    def test_concurrent_log_calls(
        self,
        mock_thread,  # noqa: ARG002
        mock_signal,  # noqa: ARG002
        mock_atexit,  # noqa: ARG002
        mock_config,
        mock_loguru_record,
    ):
        """Test concurrent log calls are handled safely."""
        sink = ParseableSink(mock_config)

        message = Mock()
        message.record = mock_loguru_record

        # Simulate concurrent access
        import threading

        results = []

        def log_worker():
            try:
                sink.log(message)
                results.append("success")
            except Exception as e:
                results.append(f"error: {e}")

        threads = []
        for _ in range(10):
            thread = threading.Thread(target=log_worker)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # All operations should succeed
        assert len(results) == 10
        assert all(result == "success" for result in results)

        # Buffer should contain all entries
        assert len(sink._buffer) == 10


class TestIntegration:
    """Integration tests for complete ParseableSink workflows."""

    @pytest.mark.asyncio
    async def test_end_to_end_logging_flow(self, mock_config, httpx_mock: HTTPXMock):
        """Test complete end-to-end logging flow."""
        with (
            patch("app.core.logging.parseable_sink.atexit.register"),
            patch("app.core.logging.parseable_sink.signal.signal"),
            patch("app.core.logging.parseable_sink.Thread"),
        ):
            # Configure for small batch and quick flush
            mock_config.parseable_batch_size = 2
            mock_config.parseable_flush_interval = 0.1

            sink = ParseableSink(mock_config)

            # Mock HTTP responses
            httpx_mock.add_response(
                url="https://test-parseable.com/api/v1/ingest",
                method="POST",
                status_code=200,
                json={"status": "success"},
            )

            # Create test log records
            records = []
            for i in range(3):
                record = {
                    "time": Mock(),
                    "level": Mock(),
                    "name": f"logger_{i}",
                    "function": f"function_{i}",
                    "line": i + 1,
                    "message": f"Test message {i}",
                    "module": f"module_{i}",
                    "file": Mock(),
                    "process": Mock(),
                    "thread": Mock(),
                    "extra": {"test_id": i},
                }
                record["time"].isoformat.return_value = f"2023-01-01T12:0{i}:00Z"
                record["level"].name = "INFO"
                record["file"].name = f"file_{i}.py"
                record["process"].id = 12345 + i
                record["thread"].id = 67890 + i
                record["thread"].name = "MainThread"
                records.append(record)

            # Manually set up client for testing
            sink._client = httpx.AsyncClient()

            try:
                # Process log messages
                for record in records:
                    message = Mock()
                    message.record = record
                    sink.log(message)

                # Manually flush to verify HTTP communication
                await sink._flush_buffer()

                # Verify requests were made
                requests = httpx_mock.get_requests()
                assert len(requests) >= 1

                # Verify request content
                request = requests[0]
                assert request.method == "POST"
                assert request.headers["X-P-Stream"] == "test-stream"

            finally:
                await sink._client.aclose()

    @pytest.mark.asyncio
    async def test_error_recovery_and_retry(self, mock_config, httpx_mock: HTTPXMock):
        """Test error recovery and retry behavior."""
        with (
            patch("app.core.logging.parseable_sink.atexit.register"),
            patch("app.core.logging.parseable_sink.signal.signal"),
            patch("app.core.logging.parseable_sink.Thread"),
            patch("builtins.print"),
        ):
            mock_config.parseable_max_retries = 2
            mock_config.parseable_retry_delay = 0.01

            sink = ParseableSink(mock_config)
            sink._client = httpx.AsyncClient()

            # First request fails, second succeeds
            httpx_mock.add_response(
                url="https://test-parseable.com/api/v1/ingest",
                method="POST",
                status_code=500,
            )
            httpx_mock.add_response(
                url="https://test-parseable.com/api/v1/ingest",
                method="POST",
                status_code=200,
            )

            # Add log entries
            sink._buffer.extend([{"test": "entry1"}, {"test": "entry2"}])

            try:
                # This should succeed after retry
                await sink._flush_buffer()

                # Verify both requests were made
                requests = httpx_mock.get_requests()
                assert len(requests) == 2

            finally:
                await sink._client.aclose()
