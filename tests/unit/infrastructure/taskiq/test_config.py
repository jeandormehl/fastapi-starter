import pytest
from pydantic import SecretStr, ValidationError

from app.infrastructure.taskiq.config import TaskiqConfiguration
from app.infrastructure.taskiq.schemas import BrokerType, TaskPriority


class TestTaskiqConfiguration:
    """Test suite for TaskiqConfiguration."""

    def test_default_configuration(self):
        """Test default configuration values."""

        config = TaskiqConfiguration(_env_file=None)

        assert config.broker_type == BrokerType.MEMORY
        assert config.broker_url is None
        assert config.result_backend_url is None
        assert config.default_queue == "default"
        assert config.default_retry_count == 3
        assert config.default_retry_delay == 60
        assert config.max_retry_delay == 3600
        assert config.task_timeout == 300
        assert config.result_ttl == 3600
        assert config.enable_metrics is True
        assert config.sanitize_logs is True

    def test_priority_queues_default(self):
        """Test default priority queue configuration."""

        config = TaskiqConfiguration(_env_file=None)

        expected_queues = {
            TaskPriority.LOW: "low_priority",
            TaskPriority.NORMAL: "normal_priority",
            TaskPriority.HIGH: "high_priority",
            TaskPriority.CRITICAL: "critical_priority",
        }

        assert config.priority_queues == expected_queues

    def test_redis_configuration(self):
        """Test Redis broker configuration."""

        config = TaskiqConfiguration(
            _env_file=None,
            broker_type=BrokerType.REDIS,
            broker_url=SecretStr("redis://localhost:6379/0"),
            result_backend_url=SecretStr("redis://localhost:6379/1"),
        )

        assert config.broker_type == BrokerType.REDIS
        assert config.broker_url.get_secret_value() == "redis://localhost:6379/0"
        assert (
            config.result_backend_url.get_secret_value() == "redis://localhost:6379/1"
        )

    def test_rabbitmq_configuration(self):
        """Test RabbitMQ broker configuration."""

        config = TaskiqConfiguration(
            _env_file=None,
            broker_type=BrokerType.RABBITMQ,
            broker_url=SecretStr("amqp://guest:guest@localhost:5672/"),
        )

        assert config.broker_type == BrokerType.RABBITMQ
        assert (
            config.broker_url.get_secret_value() == "amqp://guest:guest@localhost:5672/"
        )

    def test_validation_retry_count_bounds(self):
        """Test retry count validation bounds."""

        # Valid values
        config = TaskiqConfiguration(_env_file=None, default_retry_count=0)
        assert config.default_retry_count == 0

        config = TaskiqConfiguration(_env_file=None, default_retry_count=10)
        assert config.default_retry_count == 10

        # Invalid values
        with pytest.raises(ValidationError):
            TaskiqConfiguration(_env_file=None, default_retry_count=-1)

        with pytest.raises(ValidationError):
            TaskiqConfiguration(_env_file=None, default_retry_count=11)

    def test_validation_positive_delays(self):
        """Test validation of positive delay values."""

        # Valid values
        config = TaskiqConfiguration(
            _env_file=None, default_retry_delay=1, max_retry_delay=1
        )
        assert config.default_retry_delay == 1
        assert config.max_retry_delay == 1

        # Invalid values
        with pytest.raises(ValidationError):
            TaskiqConfiguration(_env_file=None, default_retry_delay=0)

        with pytest.raises(ValidationError):
            TaskiqConfiguration(_env_file=None, max_retry_delay=0)

    def test_encryption_configuration(self):
        """Test encryption configuration."""

        config = TaskiqConfiguration(
            _env_file=None,
            enable_task_encryption=True,
            encryption_key=SecretStr("test-encryption-key-32-chars-long"),
        )

        assert config.enable_task_encryption is True
        assert (
            config.encryption_key.get_secret_value()
            == "test-encryption-key-32-chars-long"
        )

    def test_metrics_retention_validation(self):
        """Test metrics retention validation."""

        config = TaskiqConfiguration(_env_file=None, metrics_retention_days=1)
        assert config.metrics_retention_days == 1

        with pytest.raises(ValidationError):
            TaskiqConfiguration(_env_file=None, metrics_retention_days=0)

    def test_result_ttl_validation(self):
        """Test result TTL validation."""

        config = TaskiqConfiguration(_env_file=None, result_ttl=60)
        assert config.result_ttl == 60

        with pytest.raises(ValidationError):
            TaskiqConfiguration(result_ttl=59)

    def test_task_timeout_validation(self):
        """Test task timeout validation."""

        config = TaskiqConfiguration(_env_file=None, task_timeout=1)
        assert config.task_timeout == 1

        with pytest.raises(ValidationError):
            TaskiqConfiguration(_env_file=None, task_timeout=0)

    @pytest.mark.parametrize("broker_type", [BrokerType.REDIS, BrokerType.RABBITMQ])
    def test_broker_url_required_for_external_brokers(self, broker_type):
        """Test that broker_url is required for non-memory brokers."""

        with pytest.raises(ValidationError, match="broker_url is required"):
            TaskiqConfiguration(
                _env_file=None, broker_type=broker_type, broker_url=None
            )

    def test_encryption_key_required_when_encryption_enabled(self):
        """Test that encryption_key is required when encryption is enabled."""

        with pytest.raises(ValidationError, match="encryption_key is required"):
            TaskiqConfiguration(_env_file=None, enable_task_encryption=True)

    def test_custom_priority_queues(self):
        """Test custom priority queue configuration."""

        custom_queues = {
            TaskPriority.LOW: "slow",
            TaskPriority.NORMAL: "normal",
            TaskPriority.HIGH: "fast",
            TaskPriority.CRITICAL: "urgent",
        }

        config = TaskiqConfiguration(_env_file=None, priority_queues=custom_queues)

        assert config.priority_queues == custom_queues

    def test_environment_variable_loading(self, monkeypatch):
        """Test loading configuration from environment variables."""

        monkeypatch.setenv("TASKIQ_BROKER_TYPE", BrokerType.REDIS)
        monkeypatch.setenv("TASKIQ_BROKER_URL", "redis://test:6379")
        monkeypatch.setenv("TASKIQ_DEFAULT_RETRY_COUNT", "5")
        monkeypatch.setenv("TASKIQ_ENABLE_METRICS", "false")

        config = TaskiqConfiguration(_env_file=None)

        assert config.broker_type == BrokerType.REDIS
        assert config.default_retry_count == 5
        assert config.enable_metrics is False
