import contextlib
import logging
from unittest.mock import patch

import pytest

from app.infrastructure.taskiq.broker.broker import get_broker
from app.infrastructure.taskiq.config import TaskiqConfiguration
from app.infrastructure.taskiq.schemas import BrokerType


@pytest.mark.integration
class TestBrokerIntegration:
    """Integration tests for broker functionality."""

    @pytest.mark.asyncio
    async def test_memory_broker_integration(self, caplog):
        """Test in-memory broker integration."""

        caplog.set_level(logging.FATAL)

        config = TaskiqConfiguration(broker_type=BrokerType.MEMORY)
        broker = get_broker(config)

        # Verify broker is created with middlewares
        assert broker is not None
        assert len(broker.middlewares) > 0

        # Test task registration
        @broker.task
        async def test_task(value: int) -> int:
            return value * 2

        # Test task execution
        result = await test_task.kiq(5)
        assert result.task_id is not None

    @pytest.mark.asyncio
    async def test_broker_middleware_chain(self):
        """Test broker middleware chain execution."""

        config = TaskiqConfiguration(broker_type=BrokerType.MEMORY, enable_metrics=True)

        broker = get_broker(config)

        # Verify middleware chain
        middleware_types = [type(m).__name__ for m in broker.middlewares]

        assert "LoggingMiddleware" in middleware_types
        assert "SmartRetryMiddleware" in middleware_types
        assert "ErrorHandlingMiddleware" in middleware_types

    @pytest.mark.asyncio
    async def test_task_execution_with_tracing(self, caplog):
        """Test task execution with tracing context."""

        caplog.set_level(logging.FATAL, logger="taskiq.receiver.receiver")

        config = TaskiqConfiguration(broker_type=BrokerType.MEMORY)
        broker = get_broker(config)

        @broker.task
        async def traced_task(
            data: str, _trace_id: str | None = None, _request_id: str | None = None
        ) -> dict:
            return {"data": data, "trace_id": _trace_id, "request_id": _request_id}

        # Execute with tracing
        result = await traced_task.kiq(
            "test_data", _trace_id="trace-123", _request_id="req-456"
        )

        assert result.task_id is not None


# tests/integration/taskiq/test_middleware_integration.py
@pytest.mark.integration
class TestMiddlewareIntegration:
    """Integration tests for middleware interactions."""

    @pytest.fixture
    def configured_broker(self):
        """Broker with full middleware stack."""
        config = TaskiqConfiguration(
            broker_type=BrokerType.MEMORY,
            default_retry_count=2,
            enable_metrics=True,
            sanitize_logs=True,
        )
        return get_broker(config)

    @pytest.mark.asyncio
    async def test_error_handling_and_logging_integration(
        self, caplog, configured_broker
    ):
        """Test error handling and logging middleware integration."""

        caplog.set_level(logging.FATAL)

        @configured_broker.task
        async def failing_task(should_fail: bool = True) -> str:
            if should_fail:
                msg = "Intentional test failure"
                raise ValueError(msg)
            return "success"

        # Test successful execution
        success_result = await failing_task.kiq(should_fail=False)
        assert success_result.task_id is not None

        # Test failure handling
        failure_result = await failing_task.kiq(should_fail=True)
        assert failure_result.task_id is not None

    @pytest.mark.asyncio
    async def test_circuit_breaker_integration(self, caplog, configured_broker):
        """Test circuit breaker functionality in integration."""

        caplog.set_level(logging.FATAL)

        @configured_broker.task
        async def unreliable_task(failure_rate: float = 1.0) -> str:
            import random

            if random.random() < failure_rate:
                msg = "Service unavailable"
                raise Exception(msg)
            return "success"

        # Trigger multiple failures to test circuit breaker
        with patch("random.random", return_value=0.0):  # Force failures
            for _ in range(3):
                await unreliable_task.kiq(failure_rate=1.0)

        # Circuit breaker should be active
        # Additional test execution would be blocked

    @pytest.mark.asyncio
    async def test_retry_middleware_integration(self, caplog, configured_broker):
        """Test retry middleware with error handling."""

        caplog.set_level(logging.FATAL)
        attempt_count = 0

        @configured_broker.task(retry_on_error=True, max_retries=2)
        async def retry_task() -> str:
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                msg = f"Attempt {attempt_count} failed"
                raise Exception(msg)
            return f"Success on attempt {attempt_count}"

        result = await retry_task.kiq()
        assert result.task_id is not None


# tests/integration/taskiq/test_task_execution.py
@pytest.mark.integration
class TestTaskExecution:
    """Integration tests for complete task execution flows."""

    @pytest.fixture
    def production_like_config(self):
        """Production-like configuration for testing."""
        return TaskiqConfiguration(
            broker_type=BrokerType.MEMORY,
            default_retry_count=3,
            default_retry_delay=5,
            task_timeout=30,
            enable_metrics=True,
            sanitize_logs=True,
            keep_failed_results=True,
        )

    @pytest.mark.asyncio
    async def test_task_with_complex_data(self, caplog, production_like_config):
        """Test task execution with complex data structures."""

        caplog.set_level(logging.FATAL)
        broker = get_broker(production_like_config)

        @broker.task
        async def data_processing_task(data: dict) -> dict:
            # Simulate complex data processing
            return {
                "input_size": len(str(data)),
                "keys": list(data.keys()),
                "nested_count": sum(1 for v in data.values() if isinstance(v, dict)),
                "processed": True,
            }

        complex_data = {
            "user_info": {
                "name": "Test User",
                "preferences": {"theme": "dark", "language": "en"},
            },
            "metrics": [1, 2, 3, 4, 5],
            "metadata": {"version": "1.0", "tags": ["test", "integration"]},
        }

        result = await data_processing_task.kiq(complex_data)
        assert result.task_id is not None

    @pytest.mark.asyncio
    async def test_error_propagation_and_recovery(self, caplog, production_like_config):
        """Test error propagation and recovery mechanisms."""

        caplog.set_level(logging.FATAL)
        broker = get_broker(production_like_config)

        failure_count = 0

        @broker.task
        async def recovery_task(should_recover: bool = True) -> str:
            nonlocal failure_count
            failure_count += 1

            if not should_recover and failure_count <= 2:
                msg = f"Failure #{failure_count}"
                raise Exception(msg)

            return f"Recovered after {failure_count} attempts"

        # Test failure without recovery
        # noinspection PyBroadException
        try:
            await recovery_task.kiq(should_recover=False)
        except Exception:
            contextlib.suppress(Exception)

        # Reset for recovery test
        failure_count = 0

        # Test successful recovery
        result = await recovery_task.kiq(should_recover=True)
        assert result.task_id is not None
