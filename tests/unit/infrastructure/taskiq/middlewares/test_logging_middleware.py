from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from app.common.utils import DataSanitizer
from app.infrastructure.taskiq.middlewares.logging_middleware import LoggingMiddleware


class TestLoggingMiddleware:
    """Test suite for LoggingMiddleware."""

    @pytest.fixture
    def middleware(self, default_config, mock_metrics_collector, mock_di_container):
        """Logging middleware fixture."""

        with patch(
            "app.infrastructure.taskiq.middlewares.logging_middleware.di",
            mock_di_container,
        ):
            return LoggingMiddleware(default_config, mock_metrics_collector)

    @pytest.fixture
    def middleware_no_metrics(self, default_config, mock_di_container):
        """Logging middleware without metrics collector."""

        with patch(
            "app.infrastructure.taskiq.middlewares.logging_middleware.di",
            mock_di_container,
        ):
            return LoggingMiddleware(default_config, None)

    def test_create_execution_context(self, middleware, sample_task_message):
        """Test execution context creation."""

        context = middleware._create_execution_context(sample_task_message)

        required_fields = [
            "task_id",
            "task_name",
            "task_labels",
            "execution_environment",
            "trace_id",
            "request_id",
            "timestamp",
            "worker_id",
            "broker_type",
        ]

        for field in required_fields:
            assert field in context

        assert context["task_id"] == sample_task_message.task_id
        assert context["task_name"] == sample_task_message.task_name
        assert context["execution_environment"] == "taskiq_worker"
        assert context["trace_id"] == "trace-123"
        assert context["request_id"] == "req-456"

    def test_sanitize_data_with_sensitive_fields(self):
        """Test data sanitization with sensitive fields."""

        data = {
            "username": "user123",
            "password": "secret123",
            "api_key": "key123",
            "token": "token123",
            "normal_field": "value",
        }

        sanitized = DataSanitizer.sanitize_data(data)

        assert sanitized["username"] == "user123"
        assert sanitized["password"] == "[REDACTED]"
        assert sanitized["api_key"] == "[REDACTED]"
        assert sanitized["token"] == "[REDACTED]"
        assert sanitized["normal_field"] == "value"

    def test_sanitize_data_truncates_long_strings(self):
        """Test data sanitization truncates long strings."""

        long_string = "x" * 1500

        sanitized = DataSanitizer.sanitize_data(long_string)

        assert len(sanitized) == 1014  # 1000 + len("...[TRUNCATED]")
        assert sanitized.endswith("...[TRUNCATED]")

    def test_sanitize_data_nested_structures(self):
        """Test data sanitization with nested structures."""

        data = {
            "level1": {
                "level2": {"password": "secret", "data": "normal"},
                "items": [{"token": "secret_token"}, {"value": "normal_value"}],
            }
        }

        sanitized = DataSanitizer.sanitize_data(data)

        assert sanitized["level1"]["level2"]["password"] == "[REDACTED]"
        assert sanitized["level1"]["level2"]["data"] == "normal"
        assert sanitized["level1"]["items"][0]["token"] == "[REDACTED]"
        assert sanitized["level1"]["items"][1]["value"] == "normal_value"

    def test_get_worker_id(self, middleware):
        """Test worker ID generation."""

        with patch("os.getpid", return_value=12345), patch("os.uname") as mock_uname:
            mock_uname_result = Mock()
            mock_uname_result.nodename = "test-node"
            mock_uname.return_value = mock_uname_result

            worker_id = middleware._get_worker_id()

            assert worker_id == "12345@test-node"

    def test_get_memory_usage_with_psutil(self, middleware):
        """Test memory usage with psutil available."""

        with patch("psutil.Process") as mock_process:
            mock_memory_info = Mock()
            mock_memory_info.rss = 1024 * 1024 * 100  # 100 MB in bytes
            mock_process.return_value.memory_info.return_value = mock_memory_info

            memory_mb = middleware._get_memory_usage()

            assert memory_mb == 100.0

    def test_get_memory_usage_without_psutil(self, middleware):
        """Test memory usage without psutil available."""

        with patch(
            "psutil.Process",
            side_effect=ImportError(),
        ):
            memory_mb = middleware._get_memory_usage()
            assert memory_mb == 0.0

    @pytest.mark.asyncio
    async def test_pre_execute_with_metrics(
        self, middleware, sample_task_message, mock_metrics_collector, mock_di_container
    ):
        """Test pre-execute with metrics collection."""

        with patch(  # noqa: SIM117
            "app.infrastructure.taskiq.middlewares.logging_middleware.di",
            mock_di_container,
        ):
            with patch.object(middleware.logger, "bind") as mock_bind:
                mock_logger = Mock()
                mock_bind.return_value = mock_logger

                result = await middleware.pre_execute(sample_task_message)

                # Verify metrics collection
                mock_metrics_collector.record_task_started.assert_called_once()

                # Verify logging
                mock_logger.info.assert_called_once()

                # Verify labels are set
                assert "_start_time" in sample_task_message.labels
                assert "_start_timestamp" in sample_task_message.labels

                assert result == sample_task_message

    @pytest.mark.asyncio
    async def test_pre_execute_without_metrics(
        self, middleware_no_metrics, sample_task_message, mock_di_container
    ):
        """Test pre-execute without metrics collection."""

        with patch(  # noqa: SIM117
            "app.infrastructure.taskiq.middlewares.logging_middleware.di",
            mock_di_container,
        ):
            with patch.object(middleware_no_metrics.logger, "bind") as mock_bind:
                mock_logger = Mock()
                mock_bind.return_value = mock_logger

                result = await middleware_no_metrics.pre_execute(sample_task_message)

                # Verify logging still occurs
                mock_logger.info.assert_called_once()

                assert result == sample_task_message

    @pytest.mark.asyncio
    async def test_post_execute_success(
        self,
        middleware,
        sample_task_message,
        sample_task_result,
        mock_metrics_collector,
        mock_di_container,
    ):
        """Test post-execute with successful result."""

        with patch(
            "app.infrastructure.taskiq.middlewares.logging_middleware.di",
            mock_di_container,
        ):
            # Set start time for duration calculation
            sample_task_message.labels["_start_time"] = 1000.0
            sample_task_message.labels["_start_timestamp"] = datetime.now(
                mock_di_container["timezone"]
            ).isoformat()

            with (
                patch("time.perf_counter", return_value=1005.0),
                patch.object(middleware.logger, "bind") as mock_bind,
            ):
                mock_logger = Mock()
                mock_bind.return_value = mock_logger

                await middleware.post_execute(sample_task_message, sample_task_result)

                # Verify metrics collection
                mock_metrics_collector.record_task_completed.assert_called_once()

                # Verify success logging
                mock_logger.info.assert_called_once()

    def test_execution_context_includes_sanitized_args(
        self, middleware, sample_task_message
    ):
        """Test execution context includes sanitized arguments when configured."""

        # Test with sanitize_logs enabled (default)
        context = middleware._create_execution_context(sample_task_message)

        assert "task_args" in context
        assert "task_kwargs" in context
        assert context["task_kwargs"]["param1"] == "value1"  # Normal field preserved

        # Test with sensitive data
        sample_task_message.kwargs["password"] = "secret123"
        context = middleware._create_execution_context(sample_task_message)

        assert context["task_kwargs"]["password"] == "[REDACTED]"

    def test_execution_context_without_sanitization(
        self, default_config, mock_di_container
    ):
        """Test execution context without sanitization."""

        with patch(
            "app.infrastructure.taskiq.middlewares.logging_middleware.di",
            mock_di_container,
        ):
            # Disable sanitization
            default_config.sanitize_logs = False
            middleware = LoggingMiddleware(default_config)

            task_message = Mock()
            task_message.task_id = "test-123"
            task_message.task_name = "test_task"
            task_message.labels = {}
            task_message.args = ["arg1"]
            task_message.kwargs = {"password": "secret123", "trace_id": "trace-123"}

            context = middleware._create_execution_context(task_message)

            # Password should not be redacted when sanitization is disabled
            assert context["task_kwargs"]["password"] == "secret123"

    @pytest.mark.asyncio
    async def test_duration_calculation_without_start_time(
        self, middleware, sample_task_message, sample_task_result, mock_di_container
    ):
        """Test duration calculation when start_time is missing."""

        with patch(  # noqa: SIM117
            "app.infrastructure.taskiq.middlewares.logging_middleware.di",
            mock_di_container,
        ):
            # Don't set start_time
            with patch.object(middleware.logger, "bind") as mock_bind:
                mock_logger = Mock()
                mock_bind.return_value = mock_logger

                await middleware.post_execute(sample_task_message, sample_task_result)

                # Verify context contains None for duration
                call_args = mock_bind.call_args[1]
                assert call_args["execution_duration_seconds"] is None
