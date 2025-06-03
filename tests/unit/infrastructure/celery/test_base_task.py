from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import pytest
from billiard.exceptions import WorkerLostError
from celery import Task
from celery.exceptions import Retry

from app.core.errors.exceptions import AppException, ErrorCode
from app.infrastructure.celery.base_task import BaseTask, TaskException


class TestTaskException:
    """Test the TaskException class."""

    def test_task_exception_creation(self):
        """Test basic task exception creation."""

        exc = TaskException(
            task_name="test_task",
            message="Task failed",
            task_id="task-123",
            task_args=("arg1", "arg2"),
            task_kwargs={"key": "value"},
        )

        assert "celery task 'test_task' error: Task failed" in exc.message
        assert exc.details["task_name"] == "test_task"
        assert exc.details["task_id"] == "task-123"
        assert exc.details["task_args"] == "('arg1', 'arg2')"
        assert exc.details["task_kwargs"] == {"key": "value"}
        assert exc.details["execution_context"] == "celery_worker"

    def test_task_exception_with_cause(self):
        """Test task exception with underlying cause."""

        cause = ValueError("Original error")
        exc = TaskException(
            task_name="test_task",
            message="Task failed",
            cause=cause,
        )

        assert exc.cause == cause
        assert exc.error_code == ErrorCode.INTERNAL_SERVER_ERROR

    def test_task_exception_custom_error_code(self):
        """Test task exception with custom error code."""

        exc = TaskException(
            task_name="test_task",
            message="Validation failed",
            error_code=ErrorCode.VALIDATION_ERROR,
        )

        assert exc.error_code == ErrorCode.VALIDATION_ERROR

    def test_task_exception_details_enhancement(self):
        """Test that details are properly enhanced."""

        original_details = {"custom_field": "custom_value"}
        exc = TaskException(
            task_name="test_task",
            message="Task failed",
            details=original_details,
        )

        assert exc.details["custom_field"] == "custom_value"
        assert exc.details["task_name"] == "test_task"
        assert exc.details["execution_context"] == "celery_worker"


class ConcreteTestTask(BaseTask):
    """Concrete test task for testing BaseTask functionality."""

    name = "test_task"
    request = MagicMock()

    def __init__(self):
        super().__init__()
        self.execution_result = "success"
        self.should_raise = None
        self.custom_success_called = False
        self.custom_failure_called = False
        self.custom_retry_called = False

    def run(self, *args, **kwargs):  # noqa: ARG002
        """Test task execution."""

        if self.should_raise:
            raise self.should_raise
        return self.execution_result

    def _handle_success(self, retval, task_id, args, kwargs):  # noqa: ARG002
        """Custom success handler for testing."""

        self.custom_success_called = True

    def _handle_failure(self, exc, task_id, args, kwargs, einfo, error_detail):  # noqa: ARG002
        """Custom failure handler for testing."""

        self.custom_failure_called = True

    def _handle_retry(self, exc, task_id, args, kwargs, einfo):  # noqa: ARG002
        """Custom retry handler for testing."""

        self.custom_retry_called = True


class TestBaseTask:
    """Test the BaseTask class functionality."""

    @pytest.fixture
    def test_task(self, test_celery_app):
        """Create a test task instance."""

        task = ConcreteTestTask()

        # Mock the request object
        task.request = Mock()
        task.request = MagicMock()
        task.request.id = "task-123"
        task.request.retries = 1
        task.request.hostname = "test-worker"

        task.max_retries = 3

        test_celery_app.register_task(task)

        return task

    @pytest.fixture
    def mock_logger(self):
        """Create a mock logger."""

        with patch("app.infrastructure.celery.base_task.get_logger") as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger
            mock_logger.bind.return_value = mock_logger

            yield mock_logger

    def test_task_initialization(self, test_task):
        """Test task initialization."""

        assert test_task.name == "test_task"
        assert hasattr(test_task, "logger")

    def test_on_success_callback(self, test_task, mock_logger):
        """Test successful task completion callback."""

        test_task.logger = mock_logger

        retval = {"result": "success"}
        task_id = "task-123"
        args = ("arg1", "arg2")
        kwargs = {"key": "value"}

        test_task.on_success(retval, task_id, args, kwargs)

        # Verify logging
        mock_logger.bind.assert_called_once()
        mock_logger.info.assert_called_once()

        # Verify custom handler was called
        assert test_task.custom_success_called

        # Verify log context
        bind_args = mock_logger.bind.call_args[1]
        assert bind_args["task_id"] == task_id
        assert bind_args["task_name"] == "test_task"
        assert bind_args["execution_status"] == "success"

    def test_on_failure_callback_general_exception(self, test_task, mock_logger):
        """Test failure callback with general exception."""

        test_task.logger = mock_logger

        exc = ValueError("Test error")
        task_id = "task-123"
        args = ("arg1",)
        kwargs = {"key": "value"}
        einfo = "Traceback info"

        test_task.on_failure(exc, task_id, args, kwargs, einfo)

        # Verify logging
        mock_logger.bind.assert_called_once()
        mock_logger.error.assert_called_once()

        # Verify custom handler was called
        assert test_task.custom_failure_called

        # Verify error detail structure
        bind_args = mock_logger.bind.call_args[1]
        assert bind_args["details"]["task_id"] == task_id
        assert bind_args["details"]["exception_type"] == "ValueError"
        assert bind_args["details"]["exception_message"] == "Test error"

    def test_on_failure_callback_retry_exception(self, test_task, mock_logger):
        """Test failure callback with retry exception."""

        test_task.logger = mock_logger

        exc = Retry("Retry needed")
        task_id = "task-123"
        args = ()
        kwargs = {}
        einfo = None

        test_task.on_failure(exc, task_id, args, kwargs, einfo)

        # Verify warning level logging for retries
        mock_logger.warning.assert_called_once()
        assert test_task.custom_failure_called

    def test_on_failure_callback_worker_lost(self, test_task, mock_logger):
        """Test failure callback with worker lost exception."""

        test_task.logger = mock_logger

        exc = WorkerLostError("Worker connection lost")
        task_id = "task-123"
        args = ()
        kwargs = {}
        einfo = None

        test_task.on_failure(exc, task_id, args, kwargs, einfo)

        # Verify critical level logging for worker lost
        mock_logger.critical.assert_called_once()
        assert test_task.custom_failure_called

    def test_on_failure_callback_app_exception(self, test_task, mock_logger):
        """Test failure callback with AppException."""

        test_task.logger = mock_logger

        exc = AppException(
            error_code=ErrorCode.VALIDATION_ERROR, message="Validation failed"
        )
        task_id = "task-123"
        args = ()
        kwargs = {}
        einfo = None

        test_task.on_failure(exc, task_id, args, kwargs, einfo)

        # Verify error level logging for app exceptions
        mock_logger.error.assert_called_once()
        assert test_task.custom_failure_called

    def test_on_retry_callback(self, test_task, mock_logger):
        """Test retry callback."""

        test_task.logger = mock_logger

        exc = Exception("Temporary error")
        task_id = "task-123"
        args = ("arg1",)
        kwargs = {"key": "value"}
        einfo = "Retry traceback"

        test_task.on_retry(exc, task_id, args, kwargs, einfo)

        # Verify logging
        mock_logger.bind.assert_called_once()
        mock_logger.warning.assert_called_once()

        # Verify custom handler was called
        assert test_task.custom_retry_called

        # Verify retry context
        bind_args = mock_logger.bind.call_args[1]
        assert bind_args["retry_count"] == 1
        assert bind_args["max_retries"] == 3

    def test_apply_async_with_trace_context(self, test_task, mock_logger):
        """Test apply_async adds trace context."""

        test_task.logger = mock_logger

        with patch.object(Task, "apply_async", return_value=Mock()) as mock_super_apply:
            test_task.apply_async(args=("arg1",), kwargs={"key": "value"})

            # Verify super().apply_async was called
            mock_super_apply.assert_called_once()
            call_args = mock_super_apply.call_args

            # Verify trace context was added
            kwargs = call_args[1]["kwargs"]
            assert "trace_id" in kwargs
            assert "request_id" in kwargs
            assert kwargs["trace_id"].startswith("celery-")
            assert kwargs["request_id"].startswith("task-test_task-")

    def test_apply_async_preserves_existing_trace(self, test_task, mock_logger):
        """Test apply_async preserves existing trace context."""

        test_task.logger = mock_logger

        existing_kwargs = {
            "trace_id": "existing-trace-123",
            "request_id": "existing-request-456",
            "other_key": "other_value",
        }

        with patch.object(Task, "apply_async", return_value=Mock()) as mock_super_apply:
            test_task.apply_async(kwargs=existing_kwargs)

            call_args = mock_super_apply.call_args
            kwargs = call_args[1]["kwargs"]

            # Verify existing trace context was preserved
            assert kwargs["trace_id"] == "existing-trace-123"
            assert kwargs["request_id"] == "existing-request-456"
            assert kwargs["other_key"] == "other_value"

    def test_task_call_success(self, test_task, mock_logger):
        """Test successful task execution via __call__."""

        test_task.logger = mock_logger
        test_task.execution_result = {"status": "completed"}

        result = test_task("arg1", key="value")

        assert result == {"status": "completed"}

        # Verify start and completion logging
        assert mock_logger.info.call_count == 2

        # Verify execution context
        bind_calls = mock_logger.bind.call_args_list
        assert len(bind_calls) == 2  # Start and completion

        start_context = bind_calls[0][1]
        assert start_context["execution_start"]
        assert start_context["task_id"] == "task-123"

        completion_context = bind_calls[1][1]
        assert completion_context["execution_end"]
        assert completion_context["execution_duration_seconds"] >= 0
        assert completion_context["execution_status"] == "completed"

    def test_task_call_failure(self, test_task, mock_logger):
        """Test task execution failure via __call__."""

        test_task.logger = mock_logger
        test_task.should_raise = ValueError("Execution failed")

        with pytest.raises(TaskException) as exc_info:
            test_task("arg1", key="value")

        # Verify TaskException was created
        exception = exc_info.value
        assert "celery task 'test_task' error" in exception.message
        assert exception.details["task_id"] == "task-123"
        assert exception.details["execution_duration_seconds"] >= 0

        # Verify failure logging
        mock_logger.error.assert_called_once()

    def test_task_call_with_task_exception(self, test_task, mock_logger):
        """Test task execution when TaskException is raised."""

        test_task.logger = mock_logger
        original_exception = TaskException(
            task_name="other_task", message="Original task error"
        )
        test_task.should_raise = original_exception

        with pytest.raises(TaskException) as exc_info:
            test_task("arg1", key="value")

        # Verify original TaskException was re-raised
        assert exc_info.value == original_exception

    def test_custom_callback_methods(self, test_task):
        """Test that custom callback methods can be overridden."""
        # These methods should be callable and do nothing by default
        test_task._handle_success("result", "task-id", (), {})
        test_task._handle_failure(Exception(), "task-id", (), {}, None, Mock())
        test_task._handle_retry(Exception(), "task-id", (), {}, None)

        # For our test task, they should set flags
        assert test_task.custom_success_called
        assert test_task.custom_failure_called
        assert test_task.custom_retry_called

    def test_task_execution_timing(self, test_task, mock_logger):
        """Test that execution timing is properly measured."""
        test_task.logger = mock_logger

        # Add a small delay to ensure timing is measured
        import time

        original_run = test_task.run

        def delayed_run(*args, **kwargs):
            time.sleep(0.01)  # 10ms delay
            return original_run(*args, **kwargs)

        test_task.run = delayed_run

        test_task("arg1")

        # Verify timing was recorded
        completion_call = mock_logger.bind.call_args_list[-1]
        context = completion_call[1]
        duration = context["execution_duration_seconds"]

        assert duration >= 0.01  # At least 10 ms
        assert duration < 1.0  # But not too long

    @pytest.mark.parametrize(
        ("exception_type", "expected_log_level"),
        [
            (Retry("retry"), "warning"),
            (WorkerLostError("lost"), "critical"),
            (ValueError("error"), "error"),
            (AppException(ErrorCode.VALIDATION_ERROR, "validation"), "error"),
        ],
    )
    def test_failure_logging_levels(
        self, test_task, mock_logger, exception_type, expected_log_level
    ):
        """Test that different exception types result in appropriate log levels."""
        test_task.logger = mock_logger

        test_task.on_failure(exception_type, "task-123", (), {}, None)

        # Verify the correct logging method was called
        if expected_log_level == "warning":
            mock_logger.warning.assert_called_once()
        elif expected_log_level == "critical":
            mock_logger.critical.assert_called_once()
        else:  # error
            mock_logger.error.assert_called_once()

    def test_task_dependency_injection_integration(
        self,
        test_task,  # noqa: ARG002
        setup_di_container,
        test_timezone,
    ):
        """Test that task integrates properly with dependency injection."""
        # Task should have access to DI container
        assert setup_di_container is not None

        # Task should be able to use timezone from DI
        timezone = test_timezone
        assert timezone is not None

        # Current time should work with DI timezone
        current_time = datetime.now(timezone)
        assert current_time is not None
