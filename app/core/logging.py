import contextlib
import sys
from typing import Any

from kink import di
from loguru import logger

from app.core.config import Configuration
from app.core.paths import ROOT_PATH
from app.domain.common.utils import DataSanitizer, StringUtils


def format_log_record(record: dict[str, Any]) -> str:
    """Custom formatter for loguru records with sensitive data sanitization."""
    record['message'] = DataSanitizer.sanitize(record['message'])

    format_string = (
        '<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | '
        '<level>{level: <8}</level> | '
        '<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | '
    )

    if 'extra' in record and 'event' in record['extra']:
        format_string += '<yellow>[{extra[event]: <20}]</yellow> | '

    format_string += '<level>{message}</level>'

    if 'extra' in record and len(record['extra']) > 0:
        record['extra'] = DataSanitizer.sanitize(record['extra'])
        format_string += '\n<lw>{extra}</lw>'

    if record.get('exception'):
        format_string += '\n{exception}'

    return format_string + '\n'


# noinspection PyBroadException
def setup_loki_handler(config: Configuration) -> None:
    """Setup Loki logging handler."""
    try:
        from loki_logger_handler.formatters.loguru_formatter import (  # type: ignore [import-untyped] #noqa: PLC0415
            LoguruFormatter,
        )
        from loki_logger_handler.loki_logger_handler import (  # type: ignore [import-untyped] #noqa: PLC0415
            LokiLoggerHandler,
        )

        auth = None
        if config.log.loki_username and config.log.loki_password:
            auth = (
                config.log.loki_username,
                config.log.loki_password.get_secret_value(),
            )

        loki_handler = LokiLoggerHandler(
            url=str(config.log.loki_url),
            labels={
                'application': StringUtils.slugify(config.app_name.lower()),
                'environment': config.app_environment.lower(),
                'version': config.app_version,
            },
            auth=auth,
            timeout=10,
            compressed=True,
            default_formatter=LoguruFormatter(),
            enable_self_errors=True,
        )

        logger.add(
            loki_handler, level=config.log.level, format='{message}', serialize=True
        )

    except ImportError:
        contextlib.suppress(ImportError)

    except Exception:
        contextlib.suppress(Exception)


# noinspection PyTypeChecker
def setup_logging() -> None:
    """Setup Loguru logging with configuration."""
    config = di[Configuration]
    log_config = config.log

    # Remove default handler
    logger.remove()

    # dev logging
    if config.app_debug and config.app_environment == 'local':
        logger.add(
            sys.stderr,
            level=log_config.level if config.app_environment != 'local' else 'TRACE',
            format=format_log_record,  # type: ignore [arg-type]
            colorize=True,
            backtrace=True,
            diagnose=True,
            enqueue=True,
        )

    # file logging
    if log_config.to_file:
        log_file_path = ROOT_PATH / log_config.file_path
        log_file_path.parent.mkdir(parents=True, exist_ok=True)

        logger.add(
            log_file_path,
            level=log_config.level,
            format=format_log_record,  # type: ignore [arg-type]
            rotation='100 MB',
            retention='30 days',
            compression='gz',
            backtrace=True,
            diagnose=True,
            enqueue=True,
        )

        logger.add(
            str(log_file_path).replace('app.log', 'error.log'),
            level='ERROR',
            format=format_log_record,  # type: ignore [arg-type]
            rotation='100 MB',
            retention='30 days',
            compression='gz',
            backtrace=True,
            diagnose=True,
            enqueue=True,
        )

    # loki handler
    if log_config.to_loki:
        setup_loki_handler(config)


def get_logger(name: str | None = None) -> Any:
    """Get a Loguru logger instance."""
    if name:
        return logger.bind(name=name)
    return logger
