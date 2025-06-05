from collections import deque
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from prisma.errors import ClientNotConnectedError

from app.core.errors.exceptions import AppException, ErrorCode
from app.infrastructure.taskiq.middlewares.error_handling_middleware import (
    CircuitBreaker,
    CircuitBreakerState,
    ErrorHandlingMiddleware,
)


class TestCircuitBreaker:
    """Test suite for CircuitBreaker."""

    def test_initial_state(self):
        """Test circuit breaker initial state."""

        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)

        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 0
        assert cb.last_failure_time is None
        assert cb.can_execute() is True

    def test_record_failure_increments_count(self, mock_di_container):
        """Test that recording failure increments count."""

        with patch(
            "app.infrastructure.taskiq.middlewares.error_handling_middleware.di",
            mock_di_container,
        ):
            cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)

            cb.record_failure()

            assert cb.failure_count == 1
            assert cb.last_failure_time is not None
            assert cb.state == CircuitBreakerState.CLOSED

    def test_circuit_opens_after_threshold(self, mock_di_container):
        """Test circuit opens after failure threshold."""

        with patch(
            "app.infrastructure.taskiq.middlewares.error_handling_middleware.di",
            mock_di_container,
        ):
            cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)

            # Record failures up to threshold
            for _ in range(3):
                cb.record_failure()

            assert cb.state == CircuitBreakerState.OPEN
            assert cb.can_execute() is False

    def test_circuit_half_open_after_timeout(self, mock_di_container):
        """Test circuit becomes half-open after recovery timeout."""

        with patch(
            "app.infrastructure.taskiq.middlewares.error_handling_middleware.di",
            mock_di_container,
        ):
            cb = CircuitBreaker(failure_threshold=3, recovery_timeout=1)

            # Trip the circuit
            for _ in range(3):
                cb.record_failure()

            assert cb.state == CircuitBreakerState.OPEN

            # Mock time progression
            future_time = datetime.now(mock_di_container["timezone"]) + timedelta(
                seconds=2
            )
            with patch(
                "app.infrastructure.taskiq.middlewares.error_handling_middleware.datetime"
            ) as mock_datetime:
                mock_datetime.now.return_value = future_time

                assert cb.can_execute() is True
                assert cb.state == CircuitBreakerState.HALF_OPEN

    def test_record_success_resets_circuit(self, mock_di_container):
        """Test that recording success resets circuit breaker."""

        with patch(
            "app.infrastructure.taskiq.middlewares.error_handling_middleware.di",
            mock_di_container,
        ):
            cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)

            # Trip the circuit
            for _ in range(3):
                cb.record_failure()

            assert cb.state == CircuitBreakerState.OPEN

            cb.record_success()

            assert cb.state == CircuitBreakerState.CLOSED
            assert cb.failure_count == 0


class TestErrorHandlingMiddleware:
    """Test suite for ErrorHandlingMiddleware."""

    @pytest.fixture
    def middleware(self, default_config, mock_di_container):
        """Error handling middleware fixture."""

        with patch(
            "app.infrastructure.taskiq.middlewares.error_handling_middleware.di",
            mock_di_container,
        ):
            return ErrorHandlingMiddleware(default_config)

    @pytest.mark.asyncio
    async def test_pre_execute_normal_case(self, middleware, sample_task_message):
        """Test normal pre-execute flow."""

        result = await middleware.pre_execute(sample_task_message)
        assert result == sample_task_message

    @pytest.mark.asyncio
    async def test_pre_execute_quarantined_task(
        self, middleware, sample_task_message, mock_di_container
    ):
        """Test pre-execute with quarantined task."""

        with patch(
            "app.infrastructure.taskiq.middlewares.error_handling_middleware.di",
            mock_di_container,
        ):
            # Quarantine the task
            middleware.quarantined_tasks.add(sample_task_message.task_name)
            middleware.quarantine_until[sample_task_message.task_name] = datetime.now(
                mock_di_container["timezone"]
            ) + timedelta(minutes=30)

            with pytest.raises(Exception, match="is quarantined"):
                await middleware.pre_execute(sample_task_message)

    @pytest.mark.asyncio
    async def test_pre_execute_expired_quarantine(
        self, middleware, sample_task_message, mock_di_container
    ):
        """Test pre-execute with expired quarantine."""

        with patch(
            "app.infrastructure.taskiq.middlewares.error_handling_middleware.di",
            mock_di_container,
        ):
            # Set expired quarantine
            middleware.quarantined_tasks.add(sample_task_message.task_name)
            middleware.quarantine_until[sample_task_message.task_name] = datetime.now(
                mock_di_container["timezone"]
            ) - timedelta(minutes=30)

            result = await middleware.pre_execute(sample_task_message)

            assert result == sample_task_message
            assert sample_task_message.task_name not in middleware.quarantined_tasks
            assert sample_task_message.task_name not in middleware.quarantine_until

    @pytest.mark.asyncio
    async def test_pre_execute_circuit_breaker_open(
        self, middleware, sample_task_message, mock_timezone
    ):
        """Test pre-execute with open circuit breaker."""

        # Force circuit breaker open
        cb = middleware.circuit_breakers[sample_task_message.task_name]
        cb.last_failure_time = datetime.now(mock_timezone) - timedelta(seconds=30)
        cb.state = CircuitBreakerState.OPEN

        with pytest.raises(Exception, match="circuit breaker is OPEN"):
            await middleware.pre_execute(sample_task_message)

    @pytest.mark.asyncio
    async def test_pre_execute_rate_limited(
        self, middleware, sample_task_message, mock_di_container
    ):
        """Test pre-execute with rate limiting."""

        with patch(
            "app.infrastructure.taskiq.middlewares.error_handling_middleware.di",
            mock_di_container,
        ):
            # Fill rate limit queue
            current_time = datetime.now(mock_di_container["timezone"])
            middleware.rate_limits[sample_task_message.task_name] = deque(
                [current_time] * 30,  # Max rate limit
                maxlen=60,
            )

            with pytest.raises(Exception, match="is rate limited"):
                await middleware.pre_execute(sample_task_message)

    @pytest.mark.asyncio
    async def test_on_error_updates_patterns(
        self, middleware, sample_task_message, sample_error_result, mock_di_container
    ):
        """Test on_error updates error patterns."""

        with patch(
            "app.infrastructure.taskiq.middlewares.error_handling_middleware.di",
            mock_di_container,
        ):
            exception = ValueError("Test error")

            await middleware.on_error(
                sample_task_message, sample_error_result, exception
            )

            assert (
                "ValueError" in middleware.error_patterns[sample_task_message.task_name]
            )
            assert (
                middleware.error_patterns[sample_task_message.task_name]["ValueError"]
                == 1
            )
            assert len(middleware.error_history[sample_task_message.task_name]) == 1

    @pytest.mark.asyncio
    async def test_on_error_circuit_breaker_failure(
        self, middleware, sample_task_message, sample_error_result
    ):
        """Test on_error records circuit breaker failure."""

        exception = ValueError("Test error")

        await middleware.on_error(sample_task_message, sample_error_result, exception)

        cb = middleware.circuit_breakers[sample_task_message.task_name]
        assert cb.failure_count == 1

    @pytest.mark.asyncio
    async def test_on_error_quarantine_decision(
        self, middleware, sample_task_message, sample_error_result, mock_di_container
    ):
        """Test on_error quarantine decision logic."""

        with patch(
            "app.infrastructure.taskiq.middlewares.error_handling_middleware.di",
            mock_di_container,
        ):
            # Simulate database connection error (should quarantine)
            exception = ClientNotConnectedError()

            await middleware.on_error(
                sample_task_message, sample_error_result, exception
            )

            assert sample_task_message.task_name in middleware.quarantined_tasks
            assert sample_task_message.task_name in middleware.quarantine_until

    @pytest.mark.asyncio
    async def test_on_error_app_exception_handling(
        self, middleware, sample_task_message, sample_error_result
    ):
        """Test on_error with AppException."""

        exception = AppException(
            error_code=ErrorCode.VALIDATION_ERROR,
            message="Validation failed",
            details={"field": "value"},
        )

        with patch.object(middleware.logger, "bind") as mock_bind:
            mock_logger = Mock()
            mock_bind.return_value = mock_logger

            await middleware.on_error(
                sample_task_message, sample_error_result, exception
            )

            # Verify AppException details are logged
            call_args = mock_bind.call_args[1]
            assert call_args["app_error_code"] == ErrorCode.VALIDATION_ERROR.value
            assert call_args["app_error_details"] == {"field": "value"}

    @pytest.mark.asyncio
    async def test_post_execute_success(
        self, middleware, sample_task_message, sample_task_result
    ):
        """Test post_execute on success."""

        await middleware.post_execute(sample_task_message, sample_task_result)

        cb = middleware.circuit_breakers[sample_task_message.task_name]
        assert cb.failure_count == 0
        assert cb.state == CircuitBreakerState.CLOSED

    def test_should_quarantine_task_by_error_type(self, middleware):
        """Test quarantine decision based on error type."""

        quarantine_error = ClientNotConnectedError()

        assert middleware._should_quarantine_task("test_task", quarantine_error) is True

        normal_error = ValueError("normal error")
        assert middleware._should_quarantine_task("test_task", normal_error) is False

    def test_should_quarantine_task_by_frequency(self, middleware, mock_di_container):
        """Test quarantine decision based on error frequency."""

        with patch(
            "app.infrastructure.taskiq.middlewares.error_handling_middleware.di",
            mock_di_container,
        ):
            task_name = "test_task"
            current_time = datetime.now(mock_di_container["timezone"])

            # Add many recent errors
            recent_errors = [
                {
                    "timestamp": current_time - timedelta(seconds=i),
                    "error_type": "ValueError",
                }
                for i in range(10)
            ]
            middleware.error_history[task_name] = deque(recent_errors, maxlen=100)

            exception = ValueError("test")
            assert middleware._should_quarantine_task(task_name, exception) is True

    def test_calculate_adaptive_delay(self, middleware, mock_di_container):
        """Test adaptive delay calculation."""

        with patch(
            "app.infrastructure.taskiq.middlewares.error_handling_middleware.di",
            mock_di_container,
        ):
            task_name = "test_task"

            # Test exponential backoff
            delay_0 = middleware._calculate_adaptive_delay(task_name, 0)
            delay_1 = middleware._calculate_adaptive_delay(task_name, 1)
            delay_2 = middleware._calculate_adaptive_delay(task_name, 2)

            assert delay_1 > delay_0
            assert delay_2 > delay_1
            assert delay_2 <= middleware.config.max_retry_delay

    def test_sanitize_data(self, middleware):
        """Test data sanitization."""

        sensitive_data = {
            "password": "secret123",
            "api_key": "key123",
            "normal_field": "value",
            "nested": {"token": "token123", "data": "normal"},
        }

        sanitized = middleware._sanitize_data(sensitive_data)

        assert sanitized["password"] == "[REDACTED]"
        assert sanitized["api_key"] == "[REDACTED]"
        assert sanitized["normal_field"] == "value"
        assert sanitized["nested"]["token"] == "[REDACTED]"
        assert sanitized["nested"]["data"] == "normal"

    def test_sanitize_data_lists(self, middleware):
        """Test data sanitization with lists."""

        data = [{"password": "secret"}, {"normal": "value"}]

        sanitized = middleware._sanitize_data(data)

        assert sanitized[0]["password"] == "[REDACTED]"
        assert sanitized[1]["normal"] == "value"

    def test_get_error_statistics(self, middleware, mock_di_container):
        """Test error statistics generation."""

        with patch(
            "app.infrastructure.taskiq.middlewares.error_handling_middleware.di",
            mock_di_container,
        ):
            # Setup some test data
            task_name = "test_task"

            # Add circuit breaker data
            cb = middleware.circuit_breakers[task_name]
            cb.failure_count = 2
            cb.last_failure_time = datetime.now(mock_di_container["timezone"])

            # Add quarantined task
            middleware.quarantined_tasks.add("quarantined_task")

            # Add error patterns
            middleware.error_patterns[task_name]["ValueError"] = 3
            middleware.error_patterns[task_name]["TypeError"] = 1

            # Add error history
            middleware.error_history[task_name] = deque(
                [
                    {
                        "timestamp": datetime.now(mock_di_container["timezone"]),
                        "error_type": "ValueError",
                    }
                ]
            )

            stats = middleware.get_error_statistics()

            assert "circuit_breakers" in stats
            assert "quarantined_tasks" in stats
            assert "error_patterns" in stats
            assert "recent_error_counts" in stats

            assert task_name in stats["circuit_breakers"]
            assert "quarantined_task" in stats["quarantined_tasks"]
            assert stats["error_patterns"][task_name]["ValueError"] == 3
            assert stats["recent_error_counts"][task_name] == 1

    def test_create_comprehensive_error_context(self, middleware, sample_task_message):
        """Test comprehensive error context creation."""

        exception = ValueError("Test error")

        context = middleware._create_comprehensive_error_context(
            sample_task_message, exception, None
        )

        required_fields = [
            "task_id",
            "task_name",
            "exception_type",
            "exception_message",
            "timestamp",
            "trace_id",
            "request_id",
            "retry_count",
        ]

        for field in required_fields:
            assert field in context

        assert context["task_id"] == sample_task_message.task_id
        assert context["task_name"] == sample_task_message.task_name
        assert context["exception_type"] == "ValueError"
        assert context["exception_message"] == "Test error"

    def test_is_rate_limited_cleanup(self, middleware, mock_di_container):
        """Test rate limiting cleanup of old entries."""

        with patch(
            "app.infrastructure.taskiq.middlewares.error_handling_middleware.di",
            mock_di_container,
        ):
            task_name = "test_task"
            current_time = datetime.now(mock_di_container["timezone"])
            old_time = current_time - timedelta(minutes=2)

            # Add old and new entries
            middleware.rate_limits[task_name] = deque(
                [old_time, current_time], maxlen=60
            )

            is_limited = middleware._is_rate_limited(task_name)

            # Old entry should be cleaned up
            assert len(middleware.rate_limits[task_name]) == 1
            assert middleware.rate_limits[task_name][0] == current_time
            assert is_limited is False
