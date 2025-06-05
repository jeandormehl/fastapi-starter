# tests/unit/infrastructure/taskiq/test_task_manager.py
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.infrastructure.taskiq.schemas import TaskPriority, TaskStatus
from app.infrastructure.taskiq.task_manager import TaskInfo, TaskManager


class TestTaskManager:
    """Test suite for TaskManager."""

    @pytest.fixture
    def mock_broker(self):
        """Mock broker for testing."""

        broker = Mock()
        broker.result_backend = Mock()
        broker.result_backend.get_result = AsyncMock()
        return broker

    @pytest.fixture
    def task_manager(self, mock_broker):
        """Task manager fixture."""

        return TaskManager(mock_broker)

    @pytest.mark.asyncio
    async def test_submit_task_success(
        self, task_manager, mock_broker, mock_di_container
    ):
        """Test successful task submission."""
        with patch("app.infrastructure.taskiq.task_manager.di", mock_di_container):
            # Setup mock task function
            mock_task_func = AsyncMock()
            mock_task_result = Mock()
            mock_task_result.task_id = "test-task-123"
            mock_task_func.kiq.return_value = mock_task_result

            mock_broker.test_task = mock_task_func

            task_id = await task_manager.submit_task(
                "test_task",
                "arg1",
                "arg2",
                priority=TaskPriority.HIGH,
                delay=60,
                param1="value1",
            )

            assert task_id == "test-task-123"

            # Verify task is registered
            assert task_id in task_manager.task_registry
            task_info = task_manager.task_registry[task_id]

            assert task_info.task_name == "test_task"
            assert task_info.status == TaskStatus.PENDING
            assert task_info.priority == TaskPriority.HIGH
            assert task_info.metadata["args"] == ("arg1", "arg2")
            assert task_info.metadata["kwargs"]["param1"] == "value1"

    @pytest.mark.asyncio
    async def test_submit_task_not_found(self, task_manager, memory_broker):
        """Test task submission with non-existent task."""

        task_manager.broker = memory_broker

        with pytest.raises(ValueError, match="task nonexistent_task not found"):
            await task_manager.submit_task("nonexistent_task")

    @pytest.mark.asyncio
    async def test_submit_task_with_eta(
        self, task_manager, mock_broker, mock_di_container
    ):
        """Test task submission with ETA."""

        with patch("app.infrastructure.taskiq.task_manager.di", mock_di_container):
            mock_task_func = AsyncMock()
            mock_task_result = Mock()
            mock_task_result.task_id = "test-task-456"
            mock_task_func.kiq.return_value = mock_task_result

            mock_broker.test_task = mock_task_func

            eta = datetime.now(mock_di_container["timezone"]) + timedelta(hours=1)

            await task_manager.submit_task("test_task", eta=eta)

            # Verify ETA was passed to task
            call_kwargs = mock_task_func.kiq.call_args[1]
            assert call_kwargs["eta"] == eta

    @pytest.mark.asyncio
    async def test_get_task_status_found(self, task_manager, mock_di_container):
        """Test getting task status for existing task."""

        with patch("app.infrastructure.taskiq.task_manager.di", mock_di_container):
            task_id = "test-task-123"
            task_info = TaskInfo(
                task_id=task_id,
                task_name="test_task",
                status=TaskStatus.PENDING,
                created_at=datetime.now(mock_di_container["timezone"]),
            )
            task_manager.task_registry[task_id] = task_info

            result = await task_manager.get_task_status(task_id)

            assert result == task_info

    @pytest.mark.asyncio
    async def test_get_task_status_not_found(self, task_manager):
        """Test getting task status for non-existent task."""

        result = await task_manager.get_task_status("nonexistent-task")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_task_status_with_result_backend(
        self, task_manager, mock_broker, mock_di_container
    ):
        """Test getting task status with result backend update."""

        with patch("app.infrastructure.taskiq.task_manager.di", mock_di_container):
            task_id = "test-task-123"
            task_info = TaskInfo(
                task_id=task_id,
                task_name="test_task",
                status=TaskStatus.RUNNING,
                created_at=datetime.now(mock_di_container["timezone"]),
            )
            task_manager.task_registry[task_id] = task_info

            # Mock successful result
            mock_result = Mock()
            mock_result.is_err = False
            mock_result.return_value = {"result": "success"}
            mock_broker.result_backend.get_result.return_value = mock_result

            result = await task_manager.get_task_status(task_id)

            assert result.status == TaskStatus.SUCCESS
            assert result.result == {"result": "success"}
            assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_get_task_status_with_failed_result(
        self, task_manager, mock_broker, mock_di_container
    ):
        """Test getting task status with failed result."""

        with patch("app.infrastructure.taskiq.task_manager.di", mock_di_container):
            task_id = "test-task-123"
            task_info = TaskInfo(
                task_id=task_id,
                task_name="test_task",
                status=TaskStatus.RUNNING,
                created_at=datetime.now(mock_di_container["timezone"]),
            )
            task_manager.task_registry[task_id] = task_info

            # Mock failed result
            mock_result = Mock()
            mock_result.is_err = True
            mock_result.log = "Task failed with error"
            mock_broker.result_backend.get_result.return_value = mock_result

            result = await task_manager.get_task_status(task_id)

            assert result.status == TaskStatus.FAILED
            assert result.error_message == "Task failed with error"

    @pytest.mark.asyncio
    async def test_cancel_task_success(self, task_manager, mock_di_container):
        """Test successful task cancellation."""

        with patch("app.infrastructure.taskiq.task_manager.di", mock_di_container):
            task_id = "test-task-123"
            task_info = TaskInfo(
                task_id=task_id,
                task_name="test_task",
                status=TaskStatus.PENDING,
                created_at=datetime.now(mock_di_container["timezone"]),
            )
            task_manager.task_registry[task_id] = task_info

            result = await task_manager.cancel_task(task_id)

            assert result is True
            assert task_info.status == TaskStatus.CANCELLED
            assert task_info.completed_at is not None

    @pytest.mark.asyncio
    async def test_cancel_task_not_found(self, task_manager):
        """Test cancelling non-existent task."""

        result = await task_manager.cancel_task("nonexistent-task")
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_task_already_completed(self, task_manager, mock_di_container):
        """Test cancelling already completed task."""

        with patch("app.infrastructure.taskiq.task_manager.di", mock_di_container):
            task_id = "test-task-123"
            task_info = TaskInfo(
                task_id=task_id,
                task_name="test_task",
                status=TaskStatus.SUCCESS,
                created_at=datetime.now(mock_di_container["timezone"]),
            )
            task_manager.task_registry[task_id] = task_info

            result = await task_manager.cancel_task(task_id)
            assert result is False

    @pytest.mark.asyncio
    async def test_retry_failed_task_success(
        self, task_manager, mock_broker, mock_di_container
    ):
        """Test successful retry of failed task."""

        with patch("app.infrastructure.taskiq.task_manager.di", mock_di_container):
            original_task_id = "failed-task-123"
            original_task_info = TaskInfo(
                task_id=original_task_id,
                task_name="test_task",
                status=TaskStatus.FAILED,
                created_at=datetime.now(mock_di_container["timezone"]),
                priority=TaskPriority.HIGH,
                metadata={"args": ("arg1", "arg2"), "kwargs": {"param1": "value1"}},
            )
            task_manager.task_registry[original_task_id] = original_task_info

            # Setup mock for new task submission
            mock_task_func = AsyncMock()
            mock_task_result = Mock()
            mock_task_result.task_id = "retry-task-456"
            mock_task_func.kiq.return_value = mock_task_result

            mock_broker.test_task = mock_task_func

            new_task_id = await task_manager.retry_failed_task(original_task_id)

            assert new_task_id == "retry-task-456"

            # Verify new task has incremented retry count
            new_task_info = task_manager.task_registry[new_task_id]
            assert new_task_info.retry_count == 1
            assert new_task_info.metadata["original_task_id"] == original_task_id

    @pytest.mark.asyncio
    async def test_retry_failed_task_not_found(self, task_manager):
        """Test retry of non-existent task."""

        result = await task_manager.retry_failed_task("nonexistent-task")
        assert result is None

    @pytest.mark.asyncio
    async def test_retry_failed_task_not_failed(self, task_manager, mock_di_container):
        """Test retry of non-failed task."""

        with patch("app.infrastructure.taskiq.task_manager.di", mock_di_container):
            task_id = "success-task-123"
            task_info = TaskInfo(
                task_id=task_id,
                task_name="test_task",
                status=TaskStatus.SUCCESS,
                created_at=datetime.now(mock_di_container["timezone"]),
            )
            task_manager.task_registry[task_id] = task_info

            result = await task_manager.retry_failed_task(task_id)
            assert result is None

    @pytest.mark.asyncio
    async def test_get_task_statistics(self, task_manager, mock_di_container):
        """Test comprehensive task statistics."""

        with patch("app.infrastructure.taskiq.task_manager.di", mock_di_container):
            current_time = datetime.now(mock_di_container["timezone"])

            # Add various test tasks
            tasks = [
                TaskInfo(
                    task_id="success-1",
                    task_name="task_a",
                    status=TaskStatus.SUCCESS,
                    created_at=current_time - timedelta(minutes=30),
                    started_at=current_time - timedelta(minutes=30),
                    completed_at=current_time - timedelta(minutes=29),
                    priority=TaskPriority.HIGH,
                ),
                TaskInfo(
                    task_id="failed-1",
                    task_name="task_a",
                    status=TaskStatus.FAILED,
                    created_at=current_time - timedelta(minutes=20),
                    priority=TaskPriority.NORMAL,
                ),
                TaskInfo(
                    task_id="pending-1",
                    task_name="task_b",
                    status=TaskStatus.PENDING,
                    created_at=current_time - timedelta(minutes=10),
                    priority=TaskPriority.LOW,
                ),
            ]

            for task in tasks:
                task_manager.task_registry[task.task_id] = task

            stats = await task_manager.get_task_statistics()

            assert stats["total_tasks"] == 3
            assert stats["status_counts"]["success"] == 1
            assert stats["status_counts"]["failed"] == 1
            assert stats["status_counts"]["pending"] == 1

            assert stats["priority_counts"]["high"] == 1
            assert stats["priority_counts"]["normal"] == 1
            assert stats["priority_counts"]["low"] == 1

            assert stats["last_hour"]["success"] == 1
            assert stats["last_day"]["success"] == 1

            assert "task_a" in stats["task_statistics"]
            assert stats["task_statistics"]["task_a"]["total"] == 2
            assert stats["task_statistics"]["task_a"]["success"] == 1
            assert stats["task_statistics"]["task_a"]["failed"] == 1

            # Success rate calculation
            expected_success_rate = (1 / 3) * 100
            assert abs(stats["success_rate"] - expected_success_rate) < 0.01

    @pytest.mark.asyncio
    async def test_cleanup_old_tasks(self, task_manager, mock_di_container):
        """Test cleanup of old task records."""

        with patch("app.infrastructure.taskiq.task_manager.di", mock_di_container):
            current_time = datetime.now(mock_di_container["timezone"])
            old_time = current_time - timedelta(days=8)

            # Add old completed task
            old_task = TaskInfo(
                task_id="old-task",
                task_name="old_task",
                status=TaskStatus.SUCCESS,
                created_at=old_time,
                completed_at=old_time,
            )
            task_manager.task_registry["old-task"] = old_task

            # Add recent task
            recent_task = TaskInfo(
                task_id="recent-task",
                task_name="recent_task",
                status=TaskStatus.SUCCESS,
                created_at=current_time,
                completed_at=current_time,
            )
            task_manager.task_registry["recent-task"] = recent_task

            await task_manager._cleanup_old_tasks()

            # Old task should be removed
            assert "old-task" not in task_manager.task_registry
            # Recent task should remain
            assert "recent-task" in task_manager.task_registry

    @pytest.mark.asyncio
    async def test_cleanup_loop_handles_exceptions(self, task_manager):
        """Test cleanup loop handles exceptions and continues."""

        call_count = 0

        async def mock_cleanup():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                msg = "Test error"
                raise Exception(msg)
            raise asyncio.CancelledError  # Stop after second call

        with (
            patch.object(task_manager, "_cleanup_old_tasks", side_effect=mock_cleanup),
            patch("asyncio.sleep", return_value=None),
            patch.object(task_manager.logger, "error") as mock_error,
        ):
            await task_manager._cleanup_loop()

            # Should log the error but continue
            mock_error.assert_called_once_with("error in cleanup loop: Test error")
            assert call_count == 2

    def test_task_info_dataclass(self, mock_di_container):
        """Test TaskInfo dataclass functionality."""
        with patch("app.infrastructure.taskiq.task_manager.di", mock_di_container):
            created_time = datetime.now(mock_di_container["timezone"])

            task_info = TaskInfo(
                task_id="test-123",
                task_name="test_task",
                status=TaskStatus.PENDING,
                created_at=created_time,
            )

            assert task_info.task_id == "test-123"
            assert task_info.task_name == "test_task"
            assert task_info.status == TaskStatus.PENDING
            assert task_info.created_at == created_time
            assert task_info.started_at is None
            assert task_info.completed_at is None
            assert task_info.priority == TaskPriority.NORMAL
            assert task_info.retry_count == 0
            assert task_info.error_message is None
            assert task_info.result is None
            assert task_info.metadata == {}
