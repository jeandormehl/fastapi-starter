from taskiq import AsyncBroker, InMemoryBroker
from taskiq.middlewares import SmartRetryMiddleware
from taskiq_aio_pika import AioPikaBroker
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

from app.core.config import Configuration
from app.infrastructure.taskiq.middlewares import (
    ErrorHandlingMiddleware,
    LoggingMiddleware,
)


class Broker:
    """Broker configuration with comprehensive middleware setup."""

    def __init__(self, config: Configuration):
        self.config = config

    def get_broker(self) -> AsyncBroker:
        """Create and configure the Taskiq broker with all middlewares."""

        # Create base broker
        broker = self._create_base_broker()

        # Add middlewares in order of execution
        broker.add_middlewares(
            *[
                # Logging should be first to capture everything
                LoggingMiddleware(
                    log_task_args=self.config.app_debug,
                    log_task_results=self.config.app_debug,
                ),
                SmartRetryMiddleware(
                    default_retry_count=5,
                    default_delay=15,
                    use_jitter=True,
                    use_delay_exponent=True,
                    max_delay_exponent=300,
                ),
                # Error handling should be last
                ErrorHandlingMiddleware(
                    capture_traceback=self.config.app_debug,
                    sanitize_sensitive_data=self.config.app_environment == "prod",
                    enable_error_metrics=True,
                ),
            ],
        )

        return broker

    def _create_base_broker(self) -> AsyncBroker:
        """Create the base broker based on configuration."""

        if self.config.taskiq_broker_type == "redis":
            return self._create_redis_broker()

        if self.config.taskiq_broker_type == "rabbitmq":
            return self._create_rabbitmq_broker()

        return InMemoryBroker()

    def _create_redis_broker(self) -> AsyncBroker:
        """Create Redis broker with result backend."""

        broker = ListQueueBroker(
            url=self.config.taskiq_broker_url.get_secret_value(),
            queue_name=self.config.taskiq_queue or f"{self.config.app_name}_tasks",
            # Redis-specific configurations
            max_connections=20,
            retry_on_timeout=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )

        # Add result backend if configured
        if self.config.taskiq_result_backend:
            result_backend = RedisAsyncResultBackend(
                redis_url=self.config.taskiq_result_backend.get_secret_value(),
                keep_results=3600,  # Keep results for 1 hour
            )
            broker = broker.with_result_backend(result_backend)

        return broker

    def _create_rabbitmq_broker(self) -> AsyncBroker:
        """Create RabbitMQ broker with result backend."""

        broker = AioPikaBroker(
            url=self.config.taskiq_broker_url.get_secret_value(),
            queue_name=self.config.taskiq_queue or f"{self.config.app_name}_tasks",
            # RabbitMQ-specific configurations
            declare_exchange=True,
            exchange_name=f"{self.config.app_name}_exchange",
            routing_key=f"{self.config.app_name}_routing",
        )

        # Add result backend if configured
        if self.config.taskiq_result_backend:
            result_backend = RedisAsyncResultBackend(
                redis_url=self.config.taskiq_result_backend.get_secret_value(),
                keep_results=3600,
            )
            broker = broker.with_result_backend(result_backend)

        return broker


def get_broker(config: Configuration) -> AsyncBroker:
    """Get the enhanced broker instance."""

    return Broker(config).get_broker()
