import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from kink import di
from loguru import logger

from app.core.config import Configuration


class LoggerConfig:
    """Configuration for logging system."""

    def __init__(self, config: Configuration) -> None:
        self.config = config

        self.log_level = config.log_level
        self.enable_json_logs = config.log_enable_json
        self.log_format = self._get_log_format()
        self.enable_file_logging = config.log_to_file
        self.log_file_path = config.log_file_path
        self.enable_parseable = config.parseable_enabled

    def _get_log_format(self) -> str:
        """Get appropriate log format based on configuration."""

        if self.enable_json_logs:
            return (
                "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} "
                "| {name}:{function}:{line} | {message} | {extra}"
            )

        return (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level> | "
            "\n<lw>{extra}</lw>"
        )


class LoggerManager:
    """Centralized logger management with consistent formatting."""

    def __init__(self, config: Configuration) -> None:
        self.config = LoggerConfig(config)
        self._initialized = False

        self._setup_logger()

    def _setup_logger(self) -> None:
        """Setup loguru logger with consistent configuration."""

        if self._initialized:
            return

        # Remove default handler
        logger.remove()

        # Add console handler
        logger.add(
            sys.stdout,
            format=self.config.log_format,
            level=self.config.log_level,
            enqueue=True,
            serialize=self.config.enable_json_logs,
        )

        # Add file handler if enabled
        if self.config.enable_file_logging:
            log_file = Path(self.config.log_file_path)
            log_file.parent.mkdir(parents=True, exist_ok=True)

            logger.add(
                str(log_file),
                format=self.config.log_format,
                level=self.config.log_level,
                rotation="10 MB",
                retention="30 days",
                enqueue=True,
                serialize=self.config.enable_json_logs,
            )

        # Add Parseable sink if enabled
        if self.config.enable_parseable:
            from app.core.logging.parseable_sink import ParseableSink

            parseable_sink = ParseableSink(self.config.config)

            logger.add(
                parseable_sink.log,
                level=self.config.log_level,
                format=(
                    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | "
                    "{name}:{function}:{line} | {extra} | {message}"
                ),
                enqueue=True,
            )

        self._initialized = True

    # noinspection PyMethodMayBeStatic
    def get_logger(self, name: str) -> "ContextualLogger":
        """Get a contextual logger instance."""

        return ContextualLogger(name)


class ContextualLogger:
    """Enhanced logger with consistent error formatting and context management."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.context: dict[str, Any] = {}

    def bind(self, **kwargs: Any) -> "ContextualLogger":
        """Create new logger instance with additional context."""

        new_logger = ContextualLogger(self.name)
        new_logger.context = {**self.context, **kwargs}

        return new_logger

    def _log(self, level: str, message: str, **kwargs: Any) -> None:
        """Internal logging method with consistent formatting."""

        extra = {
            "logger_name": self.name,
            "timestamp": datetime.now(di["timezone"]).isoformat(),
            **self.context,
            **kwargs,
        }

        bound_logger = logger.bind(**extra)
        getattr(bound_logger, level.lower())(message)

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log debug message."""

        self._log("DEBUG", message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        """Log info message."""

        self._log("INFO", message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        """Log warning message."""

        self._log("WARNING", message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        """Log error message with enhanced context."""

        self._log("ERROR", message, **kwargs)

    def critical(self, message: str, **kwargs: Any) -> None:
        """Log critical message."""

        self._log("CRITICAL", message, **kwargs)

    def log_exception(
        self,
        exc: Exception,
        message: str = "exception occurred",
        include_traceback: bool = True,
        **kwargs: Any,
    ) -> None:
        """Log exception with standardized format."""

        import traceback

        exception_data = {
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            **kwargs,
        }

        if include_traceback:
            exception_data["traceback"] = traceback.format_exc()

        self.error(message, **exception_data)

    def log_api_request(
        self,
        method: str,
        url: str,
        status_code: int | None = None,
        duration_ms: float | None = None,
        **kwargs: Any,
    ) -> None:
        """Log API request with standardized format."""

        request_data = {"request_method": method, "request_url": url, **kwargs}

        if status_code is not None:
            request_data["status_code"] = str(status_code)

        if duration_ms is not None:
            request_data["duration_ms"] = str(duration_ms)

        if status_code and status_code >= 400:
            self.error("api request failed", **request_data)
        else:
            self.info("api request", **request_data)


# Global logger manager instance
_logger_manager: LoggerManager | None = None


def initialize_logging(config: Configuration) -> None:
    """Initialize the global logging system."""

    global _logger_manager  # noqa: PLW0603

    if _logger_manager is None:
        _logger_manager = LoggerManager(config)


def get_logger(name: str) -> ContextualLogger:
    """Get a logger instance for the given name."""

    if _logger_manager is None:
        err = "logging not initialized. call `initialize_logging()` first."
        raise RuntimeError(err)

    return _logger_manager.get_logger(name)
