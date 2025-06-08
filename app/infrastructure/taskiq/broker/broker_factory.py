from taskiq import AsyncBroker, InMemoryBroker
from taskiq_aio_pika import AioPikaBroker
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

from app.common.logging import get_logger
from app.infrastructure.taskiq.config import TaskiqConfiguration
from app.infrastructure.taskiq.schemas import BrokerType


class BrokerFactory:
    """Broker factory."""

    def __init__(self, config: TaskiqConfiguration) -> None:
        self.config = config
        self.logger = get_logger(__name__)

    def create_broker(self) -> AsyncBroker:
        """Create broker with comprehensive configuration."""

        try:
            broker = self._create_base_broker()

            # Add result backend if configured
            if self.config.result_backend_url:
                result_backend = self._create_result_backend()
                broker = broker.with_result_backend(result_backend)

            self.logger.info(
                f"successfully created {self.config.broker_type} broker",
                extra={"broker_type": self.config.broker_type.value},
            )

            return broker

        except Exception as e:
            self.logger.error(f"failed to create broker: {e}")
            raise

    def _create_base_broker(self) -> AsyncBroker:
        """Create the base broker based on configuration."""

        if self.config.broker_type == BrokerType.REDIS:
            return self._create_redis_broker()
        if self.config.broker_type == BrokerType.RABBITMQ:
            return self._create_rabbitmq_broker()
        return InMemoryBroker()

    def _create_redis_broker(self) -> AsyncBroker:
        """Create Redis broker with advanced configuration."""

        broker_config = {
            "url": self.config.broker_url.get_secret_value(),
            "queue_name": self.config.default_queue,
            "retry_on_timeout": self.config.retry_on_timeout,
        }

        return ListQueueBroker(**broker_config)

    def _create_rabbitmq_broker(self) -> AsyncBroker:
        """Create RabbitMQ broker with advanced configuration."""

        broker_config = {
            "url": self.config.broker_url.get_secret_value(),
            "queue_name": self.config.default_queue,
            "declare_exchange": True,
            "exchange_name": f"{self.config.default_queue}_exchange",
            "routing_key": f"{self.config.default_queue}_routing",
            "heartbeat": 60,
        }

        return AioPikaBroker(**broker_config)

    def _create_result_backend(self) -> RedisAsyncResultBackend:
        """Create result backend with configuration."""

        return RedisAsyncResultBackend(
            redis_url=self.config.result_backend_url.get_secret_value(),
            keep_results=self.config.result_ttl,
            # serializer="json",
        )
