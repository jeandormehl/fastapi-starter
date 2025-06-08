import sys
from unittest.mock import Mock, patch

import pytest

from app.common.logging.logger import (
    ContextualLogger,
    LoggerConfig,
    LoggerManager,
    get_logger,
    initialize_logging,
)


class MockConfiguration:
    """Mock configuration for testing."""

    def __init__(self):
        self.log_level = "INFO"
        self.log_enable_json = False
        self.log_to_file = False
        self.log_file_path = "/tmp/test.log"
        self.parseable_enabled = False


class TestLoggerConfig:
    """Tests for LoggerConfig class."""

    def test_logger_config_initialization(self):
        """Test LoggerConfig initialization with basic configuration."""
        config = MockConfiguration()
        logger_config = LoggerConfig(config)

        assert logger_config.log_level == "INFO"
        assert logger_config.enable_json_logs is False
        assert logger_config.enable_file_logging is False
        assert logger_config.log_file_path == "/tmp/test.log"
        assert logger_config.enable_parseable is False

    def test_logger_config_json_format(self):
        """Test log format for JSON logging."""
        config = MockConfiguration()
        config.log_enable_json = True
        logger_config = LoggerConfig(config)

        expected_format = (
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} "
            "| {name}:{function}:{line} | {message} | {extra}"
        )
        assert logger_config.log_format == expected_format

    def test_logger_config_text_format(self):
        """Test log format for text logging."""
        config = MockConfiguration()
        config.log_enable_json = False
        logger_config = LoggerConfig(config)

        expected_format = (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level> | "
            "\n<lw>{extra}</lw>"
        )
        assert logger_config.log_format == expected_format


class TestLoggerManager:
    """Tests for LoggerManager class."""

    @patch("app.common.logging.logger.logger")
    def test_logger_manager_initialization(self, _mock_loguru_logger):  # noqa: PT019
        """Test LoggerManager initialization."""

        config = MockConfiguration()
        logger_manager = LoggerManager(config)

        assert logger_manager.config.log_level == "INFO"
        assert logger_manager._initialized is True

    @patch("app.common.logging.logger.logger")
    def test_logger_manager_setup_console_only(self, mock_loguru_logger):
        """Test logger setup with console output only."""

        config = MockConfiguration()
        LoggerManager(config)

        # Verify logger.remove() was called
        mock_loguru_logger.remove.assert_called_once()

        # Verify logger.add() was called for console
        calls = mock_loguru_logger.add.call_args_list
        assert len(calls) >= 1

        # Check console handler
        console_call = calls[0]
        assert console_call[0][0] == sys.stdout

    @patch("app.common.logging.logger.logger")
    @patch("pathlib.Path.mkdir")
    def test_logger_manager_setup_with_file_logging(
        self, mock_mkdir, mock_loguru_logger
    ):
        """Test logger setup with file logging enabled."""

        config = MockConfiguration()
        config.log_to_file = True
        config.log_file_path = "/tmp/app.log"

        LoggerManager(config)

        # Verify directory creation
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)

        # Verify two add calls: console + file
        assert mock_loguru_logger.add.call_count >= 2

    @patch("app.common.logging.logger.logger")
    def test_logger_manager_setup_with_parseable(self, mock_loguru_logger):
        """Test logger setup with Parseable sink enabled."""

        config = MockConfiguration()
        config.parseable_enabled = True

        with patch("app.common.logging.parseable_sink.ParseableSink") as mock_parseable:
            mock_sink_instance = Mock()
            mock_parseable.return_value = mock_sink_instance

            LoggerManager(config)

            # Verify Parseable sink was created and added
            mock_parseable.assert_called_once_with(config)
            assert mock_loguru_logger.add.call_count >= 2

    @patch("app.common.logging.logger.logger")
    def test_logger_manager_multiple_initialization(self, mock_loguru_logger):
        """Test that multiple initializations don't duplicate setup."""

        config = MockConfiguration()
        logger_manager = LoggerManager(config)

        # Reset call count
        mock_loguru_logger.reset_mock()

        # Second setup should be skipped
        logger_manager._setup_logger()

        # No additional setup calls should be made
        mock_loguru_logger.remove.assert_not_called()
        mock_loguru_logger.add.assert_not_called()

    @patch("app.common.logging.logger.logger")
    def test_get_logger_returns_contextual_logger(self, _mock_loguru_logger):  # noqa: PT019
        """Test that get_logger returns ContextualLogger instance."""

        config = MockConfiguration()
        logger_manager = LoggerManager(config)

        contextual_logger = logger_manager.get_logger("test_logger")

        assert isinstance(contextual_logger, ContextualLogger)
        assert contextual_logger.name == "test_logger"


class TestContextualLogger:
    """Tests for ContextualLogger class."""

    def test_contextual_logger_initialization(self):
        """Test ContextualLogger initialization."""

        logger = ContextualLogger("test_logger")

        assert logger.name == "test_logger"
        assert logger.context == {}

    def test_contextual_logger_bind(self):
        """Test contextual logger binding."""

        logger = ContextualLogger("test")

        bound_logger = logger.bind(user_id=123, action="login")

        assert bound_logger.name == "test"
        assert bound_logger.context == {"user_id": 123, "action": "login"}

        # Original logger should be unchanged
        assert logger.context == {}

    def test_contextual_logger_bind_chaining(self):
        """Test that binding creates new instances and can be chained."""

        logger = ContextualLogger("test")

        bound1 = logger.bind(key1="value1")
        bound2 = bound1.bind(key2="value2")

        assert logger.context == {}
        assert bound1.context == {"key1": "value1"}
        assert bound2.context == {"key1": "value1", "key2": "value2"}

    @patch("app.common.logging.logger.logger")
    @patch("kink.di")
    def test_contextual_logger_debug(self, mock_di, mock_loguru_logger):
        """Test debug logging method."""

        mock_timezone = Mock()
        mock_di.__getitem__.return_value = mock_timezone
        mock_datetime = Mock()
        mock_datetime.now.return_value.isoformat.return_value = "2023-01-01T12:00:00"

        with patch("app.common.logging.logger.datetime", mock_datetime):
            logger = ContextualLogger("test_logger")
            logger.context = {"user_id": 123}

            mock_bound = Mock()
            mock_loguru_logger.bind.return_value = mock_bound

            logger.debug("Debug message", extra_key="extra_value")

            # Verify correct binding
            expected_extra = {
                "logger_name": "test_logger",
                "timestamp": "2023-01-01T12:00:00",
                "user_id": 123,
                "extra_key": "extra_value",
            }
            mock_loguru_logger.bind.assert_called_once_with(**expected_extra)
            mock_bound.debug.assert_called_once_with("Debug message")

    @patch("app.common.logging.logger.logger")
    @patch("kink.di")
    def test_contextual_logger_all_levels(self, mock_di, mock_loguru_logger):
        """Test all logging levels."""

        mock_timezone = Mock()
        mock_di.__getitem__.return_value = mock_timezone
        mock_datetime = Mock()
        mock_datetime.now.return_value.isoformat.return_value = "2023-01-01T12:00:00"

        with patch("app.common.logging.logger.datetime", mock_datetime):
            logger = ContextualLogger("test")
            mock_bound = Mock()
            mock_loguru_logger.bind.return_value = mock_bound

            # Test all logging levels
            logger.debug("Debug")
            logger.info("Info")
            logger.warning("Warning")
            logger.error("Error")
            logger.critical("Critical")

            # Verify all methods were called
            mock_bound.debug.assert_called_once_with("Debug")
            mock_bound.info.assert_called_once_with("Info")
            mock_bound.warning.assert_called_once_with("Warning")
            mock_bound.error.assert_called_once_with("Error")
            mock_bound.critical.assert_called_once_with("Critical")

    @patch("app.common.logging.logger.logger")
    @patch("kink.di")
    def test_log_exception_with_traceback(self, mock_di, mock_loguru_logger):
        """Test exception logging with traceback."""

        mock_timezone = Mock()
        mock_di.__getitem__.return_value = mock_timezone
        mock_datetime = Mock()
        mock_datetime.now.return_value.isoformat.return_value = "2023-01-01T12:00:00"

        with (
            patch("app.common.logging.logger.datetime", mock_datetime),
            patch("traceback.format_exc", return_value="Traceback info"),
        ):
            logger = ContextualLogger("test")
            mock_bound = Mock()
            mock_loguru_logger.bind.return_value = mock_bound

            test_exception = ValueError("Test error")
            logger.log_exception(test_exception, "Custom message")

            # Verify exception data in binding
            call_args = mock_loguru_logger.bind.call_args[1]
            assert call_args["exception_type"] == "ValueError"
            assert call_args["exception_message"] == "Test error"
            assert call_args["traceback"] == "Traceback info"

            mock_bound.error.assert_called_once_with("Custom message")

    @patch("app.common.logging.logger.logger")
    @patch("kink.di")
    def test_log_exception_without_traceback(self, mock_di, mock_loguru_logger):
        """Test exception logging without traceback."""

        mock_timezone = Mock()
        mock_di.__getitem__.return_value = mock_timezone
        mock_datetime = Mock()
        mock_datetime.now.return_value.isoformat.return_value = "2023-01-01T12:00:00"

        with patch("app.common.logging.logger.datetime", mock_datetime):
            logger = ContextualLogger("test")
            mock_bound = Mock()
            mock_loguru_logger.bind.return_value = mock_bound

            test_exception = RuntimeError("Runtime error")
            logger.log_exception(test_exception, include_traceback=False)

            # Verify no traceback in binding
            call_args = mock_loguru_logger.bind.call_args[1]
            assert "traceback" not in call_args
            assert call_args["exception_type"] == "RuntimeError"

    @patch("app.common.logging.logger.logger")
    @patch("kink.di")
    def test_log_api_request_success(self, mock_di, mock_loguru_logger):
        """Test API request logging for successful requests."""

        mock_timezone = Mock()
        mock_di.__getitem__.return_value = mock_timezone
        mock_datetime = Mock()
        mock_datetime.now.return_value.isoformat.return_value = "2023-01-01T12:00:00"

        with patch("app.common.logging.logger.datetime", mock_datetime):
            logger = ContextualLogger("test")
            mock_bound = Mock()
            mock_loguru_logger.bind.return_value = mock_bound

            logger.log_api_request(
                "GET", "/api/users", status_code=200, duration_ms=150.5
            )

            call_args = mock_loguru_logger.bind.call_args[1]
            assert call_args["request_method"] == "GET"
            assert call_args["request_url"] == "/api/users"
            assert call_args["status_code"] == "200"
            assert call_args["duration_ms"] == "150.5"

            mock_bound.info.assert_called_once_with("api request")

    @patch("app.common.logging.logger.logger")
    @patch("kink.di")
    def test_log_api_request_error(self, mock_di, mock_loguru_logger):
        """Test API request logging for error responses."""

        mock_timezone = Mock()
        mock_di.__getitem__.return_value = mock_timezone
        mock_datetime = Mock()
        mock_datetime.now.return_value.isoformat.return_value = "2023-01-01T12:00:00"

        with patch("app.common.logging.logger.datetime", mock_datetime):
            logger = ContextualLogger("test")
            mock_bound = Mock()
            mock_loguru_logger.bind.return_value = mock_bound

            logger.log_api_request(
                "POST", "/api/users", status_code=400, duration_ms=75.2
            )

            mock_bound.error.assert_called_once_with("api request failed")


class TestGlobalFunctions:
    """Tests for global logging functions."""

    def test_initialize_logging_first_time(self):
        """Test first-time logging initialization."""

        config = MockConfiguration()

        # Reset global state
        import app.common.logging.logger

        app.common.logging.logger._logger_manager = None

        with patch("app.common.logging.logger.LoggerManager") as mock_manager_class:
            initialize_logging(config)
            mock_manager_class.assert_called_once_with(config)

    def test_initialize_logging_already_initialized(self):
        """Test that re-initialization is handled gracefully."""

        config = MockConfiguration()

        with patch("app.common.logging.logger.LoggerManager") as mock_manager_class:
            # First initialization
            initialize_logging(config)
            mock_manager_class.reset_mock()

            # Second initialization should not create new manager
            initialize_logging(config)
            mock_manager_class.assert_not_called()

    def test_get_logger_before_initialization(self):
        """Test get_logger raises error when not initialized."""

        # Reset global state
        import app.common.logging.logger

        app.common.logging.logger._logger_manager = None

        with pytest.raises(RuntimeError, match="logging not initialized"):
            get_logger("test")
