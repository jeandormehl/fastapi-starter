from typing import Any

from taskiq import AsyncBroker
from taskiq.middlewares import SmartRetryMiddleware

from app.infrastructure.taskiq.broker.broker_factory import BrokerFactory
from app.infrastructure.taskiq.config import TaskiqConfiguration
from app.infrastructure.taskiq.middlewares import (
    ErrorHandlingMiddleware,
    LoggingMiddleware,
    TaskLoggingMiddleware,
)


class Broker:
    """Broker with comprehensive middleware and monitoring."""

    def __init__(self, config: TaskiqConfiguration) -> None:
        self.taskiq_config = config
        self.broker_factory = BrokerFactory(self.taskiq_config)

    def create_broker(self) -> AsyncBroker:
        """Create fully configured broker with all enhancements."""

        # Create base broker
        broker = self.broker_factory.create_broker()

        # Add middlewares
        middlewares = [
            # Logging middleware (first to capture everything)
            TaskLoggingMiddleware(config=self.taskiq_config),
            LoggingMiddleware(config=self.taskiq_config),
            # Retry middleware
            SmartRetryMiddleware(
                default_retry_count=self.taskiq_config.default_retry_count,
                default_delay=self.taskiq_config.default_retry_delay,
                use_jitter=True,
                use_delay_exponent=True,
                max_delay_exponent=self.taskiq_config.max_retry_delay,
            ),
            # Error handling middleware (last to handle all errors)
            ErrorHandlingMiddleware(config=self.taskiq_config),
        ]

        broker.add_middlewares(*middlewares)

        return broker

    def get_metrics_collector(self) -> Any:
        """Get the metrics collector for external monitoring."""

        return None


def get_broker(config: TaskiqConfiguration) -> AsyncBroker:
    """Create broker instance."""

    broker = Broker(config)
    return broker.create_broker()
