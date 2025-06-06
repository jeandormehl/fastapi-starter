from unittest.mock import Mock, patch

import pytest
from taskiq import InMemoryBroker

from app.core.errors.errors import AppError, ErrorCode
from app.infrastructure.taskiq.broker.broker_factory import BrokerFactory


class TestBrokerFactory:
    """Test suite for BrokerFactory."""

    def test_create_memory_broker(self, default_config):
        """Test creation of in-memory broker."""

        factory = BrokerFactory(default_config)
        broker = factory.create_broker()

        assert isinstance(broker, InMemoryBroker)

    @patch("app.infrastructure.taskiq.broker.broker_factory.RedisAsyncResultBackend")
    @patch("app.infrastructure.taskiq.broker.broker_factory.ListQueueBroker")
    def test_create_redis_broker(
        self, mock_redis_broker, mock_result_backend, redis_config
    ):
        """Test creation of Redis broker."""

        mock_broker_instance = Mock()
        mock_redis_broker.with_result_backend(mock_result_backend)
        mock_redis_broker.return_value = mock_broker_instance

        factory = BrokerFactory(redis_config)
        factory.create_broker()

        mock_redis_broker.assert_called_once_with(
            url=redis_config.broker_url.get_secret_value(),
            queue_name=redis_config.default_queue,
            retry_on_timeout=redis_config.retry_on_timeout,
        )
        mock_result_backend.assert_called_once()

    @patch("app.infrastructure.taskiq.broker.broker_factory.RedisAsyncResultBackend")
    @patch("app.infrastructure.taskiq.broker.broker_factory.AioPikaBroker")
    def test_create_rabbitmq_broker(
        self, mock_rabbitmq_broker, mock_result_backend, rabbitmq_config
    ):
        """Test creation of RabbitMQ broker."""

        mock_broker_instance = Mock()
        mock_rabbitmq_broker.return_value = mock_broker_instance

        factory = BrokerFactory(rabbitmq_config)
        factory.create_broker()

        expected_config = {
            "url": rabbitmq_config.broker_url.get_secret_value(),
            "queue_name": rabbitmq_config.default_queue,
            "declare_exchange": True,
            "exchange_name": f"{rabbitmq_config.default_queue}_exchange",
            "routing_key": f"{rabbitmq_config.default_queue}_routing",
            "heartbeat": 60,
        }

        mock_rabbitmq_broker.assert_called_once_with(**expected_config)
        mock_result_backend.assert_called_once()

    @patch("app.infrastructure.taskiq.broker.broker_factory.RedisAsyncResultBackend")
    def test_create_broker_with_result_backend(self, mock_result_backend, redis_config):
        """Test broker creation with result backend."""

        mock_backend_instance = Mock()
        mock_result_backend.return_value = mock_backend_instance

        factory = BrokerFactory(redis_config)

        with patch.object(factory, "_create_base_broker") as mock_base_broker:
            mock_broker = Mock()
            mock_broker_with_backend = Mock()
            mock_broker.with_result_backend.return_value = mock_broker_with_backend
            mock_base_broker.return_value = mock_broker

            result = factory.create_broker()

            mock_result_backend.assert_called_once_with(
                redis_url=redis_config.result_backend_url.get_secret_value(),
                keep_results=redis_config.result_ttl,
            )
            mock_broker.with_result_backend.assert_called_once_with(
                mock_backend_instance
            )
            assert result == mock_broker_with_backend

    def test_create_broker_handles_exceptions(self, default_config):
        """Test broker creation exception handling."""

        factory = BrokerFactory(default_config)

        with (
            patch.object(
                factory,
                "_create_base_broker",
                side_effect=AppError(ErrorCode.INTERNAL_SERVER_ERROR, "Test error"),
            ),
            pytest.raises(AppError, match="Test error"),
        ):
            factory.create_broker()

    def test_logging_on_successful_creation(self, default_config):
        """Test logging on successful broker creation."""

        factory = BrokerFactory(default_config)

        with patch.object(factory.logger, "info") as mock_info:
            factory.create_broker()

            mock_info.assert_called_once_with(
                f"successfully created {default_config.broker_type} broker",
                extra={"broker_type": default_config.broker_type.value},
            )

    def test_logging_on_failed_creation(self, default_config):
        """Test logging on failed broker creation."""

        factory = BrokerFactory(default_config)

        with (
            patch.object(factory.logger, "error") as mock_error,
            patch.object(
                factory,
                "_create_base_broker",
                side_effect=AppError(ErrorCode.INTERNAL_SERVER_ERROR, "Test error"),
            ),
        ):
            with pytest.raises(AppError):
                factory.create_broker()

            mock_error.assert_called_once_with("failed to create broker: Test error")

    def test_redis_broker_configuration_parameters(self, redis_config):
        """Test Redis broker receives correct configuration parameters."""

        factory = BrokerFactory(redis_config)

        with patch(
            "app.infrastructure.taskiq.broker.broker_factory.ListQueueBroker"
        ) as mock_redis:
            factory._create_redis_broker()

            expected_config = {
                "url": redis_config.broker_url.get_secret_value(),
                "queue_name": redis_config.default_queue,
                "retry_on_timeout": redis_config.retry_on_timeout,
            }

            mock_redis.assert_called_once_with(**expected_config)

    def test_rabbitmq_broker_configuration_parameters(self, rabbitmq_config):
        """Test RabbitMQ broker receives correct configuration parameters."""

        factory = BrokerFactory(rabbitmq_config)

        with patch(
            "app.infrastructure.taskiq.broker.broker_factory.AioPikaBroker"
        ) as mock_rabbitmq:
            factory._create_rabbitmq_broker()

            expected_config = {
                "url": rabbitmq_config.broker_url.get_secret_value(),
                "queue_name": rabbitmq_config.default_queue,
                "declare_exchange": True,
                "exchange_name": f"{rabbitmq_config.default_queue}_exchange",
                "routing_key": f"{rabbitmq_config.default_queue}_routing",
                "heartbeat": 60,
            }

            mock_rabbitmq.assert_called_once_with(**expected_config)

    def test_result_backend_configuration(self, redis_config):
        """Test result backend configuration parameters."""

        factory = BrokerFactory(redis_config)

        with patch(
            "app.infrastructure.taskiq.broker.broker_factory.RedisAsyncResultBackend"
        ) as mock_backend:
            factory._create_result_backend()

            mock_backend.assert_called_once_with(
                redis_url=redis_config.result_backend_url.get_secret_value(),
                keep_results=redis_config.result_ttl,
            )
