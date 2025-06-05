from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from taskiq import InMemoryBroker, TaskiqMessage
from taskiq.result import TaskiqResult

from app.infrastructure.taskiq.config import TaskiqConfiguration
from app.infrastructure.taskiq.schemas import (
    BrokerType,
    TaskExecutionMetrics,
    TaskStatus,
)


@pytest.fixture
def mock_timezone():
    """Mock timezone for consistent testing."""

    return timezone.utc


@pytest.fixture
def mock_di_container(mock_timezone):
    """Mock dependency injection container."""

    container = Mock()
    container.__getitem__ = Mock(return_value=mock_timezone)

    return container


@pytest.fixture
def default_config():
    """Default Taskiq configuration for testing."""

    return TaskiqConfiguration(
        broker_type=BrokerType.MEMORY,
        default_queue="test_queue",
        default_retry_count=3,
        default_retry_delay=60,
        max_retry_delay=3600,
        task_timeout=300,
        result_ttl=3600,
        enable_metrics=True,
        sanitize_logs=True,
    )


@pytest.fixture
def redis_config():
    """Redis Taskiq configuration for testing."""

    return TaskiqConfiguration(
        broker_type=BrokerType.REDIS,
        broker_url="redis://localhost:6379/0",
        result_backend_url="redis://localhost:6379/1",
        default_queue="test_redis_queue",
    )


@pytest.fixture
def rabbitmq_config():
    """RabbitMQ Taskiq configuration for testing."""

    return TaskiqConfiguration(
        broker_type=BrokerType.RABBITMQ,
        broker_url="amqp://guest:guest@localhost:5672/",
        default_queue="test_rabbitmq_queue",
    )


@pytest.fixture
def sample_task_message():
    """Sample TaskiqMessage for testing."""

    return TaskiqMessage(
        task_id="test-task-123",
        task_name="test_task",
        args=["arg1", "arg2"],
        kwargs={"param1": "value1", "trace_id": "trace-123", "request_id": "req-456"},
        labels={"priority": "normal", "queue": "default"},
    )


@pytest.fixture
def sample_task_result():
    """Sample successful TaskiqResult for testing."""

    return TaskiqResult(
        is_err=False,
        log="Task completed successfully",
        return_value={"result": "success", "data": "processed"},
        execution_time=1,
    )


@pytest.fixture
def sample_error_result():
    """Sample failed TaskiqResult for testing."""

    return TaskiqResult(
        is_err=True,
        log="Task failed with ValueError: test error",
        return_value=None,
        execution_time=1,
    )


@pytest.fixture
def mock_metrics_collector():
    """Mock metrics collector for testing."""

    collector = Mock()
    collector.record_task_started = AsyncMock()
    collector.record_task_completed = AsyncMock()
    collector.record_task_failed = AsyncMock()
    return collector


@pytest.fixture
def sample_execution_metrics():
    """Sample task execution metrics."""

    return TaskExecutionMetrics(
        task_id="test-task-123",
        task_name="test_task",
        start_time=datetime.now(timezone.utc),
        status=TaskStatus.RUNNING,
    )


@pytest.fixture
def memory_broker():
    """In-memory broker for testing."""

    return InMemoryBroker()


# noinspection HttpUrlsUsage
@pytest.fixture
def mock_request():
    """Mock FastAPI request for middleware testing."""

    request = Mock()
    request.method = "POST"
    request.url.path = "/api/test"
    request.url = Mock()
    request.url.__str__ = Mock(return_value="http://test.com/api/test")
    request.query_params = {}
    request.headers = {"user-agent": "test-agent", "content-type": "application/json"}
    request.client.host = "127.0.0.1"
    request.state = Mock()

    return request
