from unittest.mock import Mock, patch

from pydantic import SecretStr
from taskiq import AsyncBroker, InMemoryBroker

from app.infrastructure.taskiq.broker.broker_factory import BrokerFactory
from app.infrastructure.taskiq.config import TaskiqConfiguration
from app.infrastructure.taskiq.schemas import BrokerType


class TestBrokerFactory:
    """Test broker factory functionality."""

    def test_create_memory_broker(self, taskiq_config: TaskiqConfiguration):
        """Test creating memory broker."""
        with patch("app.infrastructure.taskiq.broker.broker_factory.get_logger"):
            taskiq_config.broker_type = BrokerType.MEMORY

            broker = BrokerFactory(taskiq_config).create_broker()

            assert broker is not None
            assert isinstance(broker, AsyncBroker | InMemoryBroker)

    def test_create_redis_broker(self, taskiq_config: TaskiqConfiguration):
        """Test creating Redis broker."""
        taskiq_config.broker_type = BrokerType.REDIS
        taskiq_config.broker_url = SecretStr("redis://localhost:6379")

        with patch(
            "app.infrastructure.taskiq.broker.broker_factory.ListQueueBroker"
        ) as mock_redis:
            mock_redis.return_value = Mock()

            broker = BrokerFactory(taskiq_config).create_broker()

            assert broker is not None
            mock_redis.assert_called_once()
