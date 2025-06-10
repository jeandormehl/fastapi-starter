from unittest.mock import Mock, patch

import pytest

from app.common.logging.logger import (
    ContextualLogger,
    LoggerConfig,
    LoggerManager,
    get_logger,
)


class TestLoggerConfig:
    """Test logger configuration."""

    def test_logger_config_initialization(self, test_config):
        """Test logger config initialization."""
        config = LoggerConfig(test_config)

        assert config.log_level == "CRITICAL"
        assert not config.enable_json_logs
        assert not config.enable_file_logging
        assert not config.enable_parseable

    def test_log_format_json_disabled(self, test_config):
        """Test log format when JSON is disabled."""
        config = LoggerConfig(test_config)
        log_format = config._get_log_format()

        # Should contain color formatting when JSON is disabled
        assert "<green>" in log_format
        assert "<level>" in log_format
        assert "<cyan>" in log_format

    def test_log_format_json_enabled(self, test_config):
        """Test log format when JSON is enabled."""
        test_config.log_enable_json = True
        config = LoggerConfig(test_config)
        log_format = config._get_log_format()

        # Should not contain color formatting when JSON is enabled
        assert "<green>" not in log_format
        assert "<level>" not in log_format
        assert "| {level} |" in log_format


class TestContextualLogger:
    """Test contextual logger functionality."""

    def test_logger_binding(self, suppress_logging):  # noqa: ARG002
        """Test logger context binding."""
        logger = ContextualLogger("test")
        bound_logger = logger.bind(test_key="test_value", user_id="123")

        assert "test_key" in bound_logger.context
        assert bound_logger.context["test_key"] == "test_value"
        assert "user_id" in bound_logger.context
        assert bound_logger.context["user_id"] == "123"

    def test_logger_methods_no_output(self, suppress_logging):
        """Test logger methods produce no output during tests."""
        logger = ContextualLogger("test")

        # These should not produce any output due to mocking
        logger.debug("debug message")
        logger.info("info message")
        logger.warning("warning message")
        logger.error("error message")
        logger.critical("critical message")

        # Verify mocked logger was called but no real logging occurred
        assert suppress_logging.bind.called

    def test_log_exception_handling(self, suppress_logging):
        """Test exception logging."""
        logger = ContextualLogger("test")

        try:
            msg = "Test exception"
            raise ValueError(msg)
        except ValueError as e:
            logger.log_exception(e, "Test exception occurred")

        # Should not raise any errors and should be mocked
        assert suppress_logging.bind.called

    def test_log_api_request(self, suppress_logging):
        """Test API request logging."""
        logger = ContextualLogger("test")

        logger.log_api_request(
            method="GET", url="/api/test", status_code=200, duration_ms=150.5
        )

        # Should be mocked and not produce output
        assert suppress_logging.bind.called


class TestLoggerManager:
    """Test logger manager functionality."""

    @patch("app.common.logging.logger.logger")
    def test_logger_manager_initialization(self, mock_loguru, test_config):
        """Test logger manager initialization."""
        LoggerManager(test_config)

        # Should remove default handler and add configured ones
        assert mock_loguru.remove.called
        assert mock_loguru.add.called

    def test_get_logger_returns_contextual_logger(self, test_config):
        """Test getting logger returns ContextualLogger."""
        with patch("app.common.logging.logger.logger"):
            manager = LoggerManager(test_config)
            test_logger = manager.get_logger("test")

            assert isinstance(test_logger, ContextualLogger)
            assert test_logger.name == "test"


class TestGlobalLoggerFunctions:
    """Test global logger functions."""

    def test_get_logger_before_initialization(self):
        """Test getting logger before initialization raises error."""
        # Clear global state
        import app.common.logging.logger

        app.common.logging.logger._logger_manager = None

        with pytest.raises(RuntimeError) as exc_info:
            get_logger("test")

        assert "logging not initialized" in str(exc_info.value)

    @patch("app.common.logging.logger._logger_manager")
    def test_get_logger_after_initialization(self, mock_manager):
        """Test getting logger after initialization."""
        mock_contextual_logger = Mock()
        mock_manager.get_logger.return_value = mock_contextual_logger

        result = get_logger("test")

        mock_manager.get_logger.assert_called_once_with("test")
        assert result == mock_contextual_logger
