from taskiq import AsyncBroker, InMemoryBroker
from taskiq_aio_pika import AioPikaBroker
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

from app.core.config import Configuration

from .base_task import BaseTask
from .middlewares import ErrorHandlingMiddleware, LoggingMiddleware


class Broker:
    def __init__(self, config: Configuration):
        self.config = config

    def __call__(self) -> AsyncBroker:
        """Get Taskiq broker instance"""

        broker = InMemoryBroker()

        # Determine broker type based on configuration
        if self.config.taskiq_broker_type == "redis":
            broker = self._get_redis_broker()

        elif self.config.taskiq_broker_type == "rabbitmq":
            broker = self._get_rabbitmq_broker()

        broker.add_middlewares(
            *[
                LoggingMiddleware(),
                ErrorHandlingMiddleware(),
            ]
        )

        return broker

    def _get_redis_broker(self) -> RedisAsyncResultBackend:
        """Get redis broker instance"""

        broker = ListQueueBroker(
            url=self.config.taskiq_broker_url.get_secret_value(),
            queue_name=self.config.taskiq_queue or f"{self.config.app_name}_tasks",
        )
        return self._get_result_backend(broker)

    def _get_rabbitmq_broker(self):
        """Get rabbitmq broker instance"""

        broker = AioPikaBroker(
            url=self.config.taskiq_broker_url.get_secret_value(),
            queue_name=self.config.taskiq_queue_name or f"{self.config.app_name}_tasks",
        )
        return self._get_result_backend(broker)

    def _get_result_backend(self, broker: AsyncBroker):
        """Get result backend if configured"""

        if self.config.taskiq_result_backend:
            result_backend = RedisAsyncResultBackend(
                redis_url=self.config.taskiq_result_backend.get_secret_value()
            )
            return broker.with_result_backend(result_backend)
        return broker


def get_broker(config: Configuration) -> AsyncBroker:
    """Get the broker instance"""

    broker = Broker(config).__call__()
    broker.task_class = BaseTask

    return broker
