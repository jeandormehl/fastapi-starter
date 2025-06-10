from unittest.mock import Mock, patch

from app.common.logging.parseable_sink import ParseableSink


# noinspection HttpUrlsUsage,PyUnusedLocal
class TestParseableSink:
    """Test Parseable sink functionality."""

    @patch("app.common.logging.parseable_sink.Thread")
    @patch("app.common.logging.parseable_sink.atexit")
    @patch("app.common.logging.parseable_sink.signal")
    def test_parseable_sink_initialization(
        self,
        mock_signal,
        mock_atexit,
        mock_thread,  # noqa: ARG002
        test_config,
    ):
        """Test Parseable sink initialization."""
        test_config.parseable_enabled = True
        test_config.parseable_url = "http://test.parseable.com"
        test_config.parseable_stream = "test-stream"

        sink = ParseableSink(test_config)

        assert sink.base_url == "http://test.parseable.com"
        assert sink.stream_name == "test-stream"
        assert sink._running is True

        # Should register cleanup handlers
        mock_atexit.register.assert_called()
        assert mock_signal.signal.call_count >= 2  # SIGTERM and SIGINT

    def test_parseable_sink_disabled_in_tests(self, test_config):
        """Test Parseable sink is disabled in test configuration."""
        assert not test_config.parseable_enabled

        # Even if we create a sink, it should not interfere with tests
        with patch("app.common.logging.parseable_sink.Thread"):
            sink = ParseableSink(test_config)

            # Should handle being disabled gracefully
            sink.log(Mock())  # Should not raise errors

    @patch("app.common.logging.parseable_sink.Thread")
    def test_log_method_error_handling(self, mock_thread, test_config):  # noqa: ARG002
        """Test log method handles errors gracefully."""
        sink = ParseableSink(test_config)

        # Mock a loguru record that might cause errors
        mock_record = Mock()
        mock_record.record = {
            "time": Mock(),
            "level": Mock(name="INFO"),
            "name": "test-logger",
            "function": "test_function",
            "line": 42,
            "message": "test message",
            "module": "test_module",
            "file": Mock(name="test.py"),
            "process": Mock(id=12345),
            "thread": Mock(id=67890, name="MainThread"),
            "extra": {"test_key": "test_value"},
        }

        mock_record.record["time"].isoformat = Mock(return_value="2023-01-01T00:00:00")

        # Should not raise exceptions even with complex record
        sink.log(mock_record)

    def test_cleanup_method(self, test_config):
        """Test cleanup method."""
        with patch("app.common.logging.parseable_sink.Thread"):
            sink = ParseableSink(test_config)

            # Should handle cleanup gracefully
            sink.cleanup()
            assert not sink._running
