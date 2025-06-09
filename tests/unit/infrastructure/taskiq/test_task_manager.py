from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.infrastructure.taskiq.schemas import TaskPriority, TaskStatus
from app.infrastructure.taskiq.task_manager import (
    TaskInfo,
    TaskManager,
    TaskManagerError,
    TaskNotFoundError,
    TaskSubmissionError,
)


class TestTaskManager:
    """Test suite for refactored TaskManager."""

    @pytest.fixture
    def mock_broker(self):
        """Mock broker for testing."""
        broker = Mock()
        broker.local_task_registry = {}
        broker.result_backend = Mock()
        broker.result_backend.get_result = AsyncMock()
        return broker

    @pytest.fixture
    def task_manager(self, mock_broker):
        """Task manager fixture."""
        return TaskManager(mock_broker, max_registry_size=5)

    @pytest.fixture
    def mock_di_container(self):
        """Mock dependency injection container."""
        container = Mock()
        container.__getitem__ = Mock(return_value=UTC)
        return container

    @pytest.fixture
    def sample_task_info(self, mock_di_container):
        """Sample task info for testing."""
        with patch("app.infrastructure.taskiq.task_manager.di", mock_di_container):
            return TaskInfo(
                task_id="test-task-123",
                task_name="test_task",
                status=TaskStatus.PENDING,
                created_at=datetime.now(UTC),
                priority=TaskPriority.NORMAL,
                metadata={"args": (), "kwargs": {}},
            )

    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(self, task_manager):
        """Test task manager start/stop lifecycle."""
        assert not task_manager._is_running

        with patch(
            "app.infrastructure.taskiq.task_manager.TaskAutodiscovery"
        ) as mock_autodiscovery:
            mock_autodiscovery.return_value.discover_and_register_tasks = Mock()

            await task_manager.start()
            assert task_manager._is_running
            assert task_manager._cleanup_task is not None

            await task_manager.stop()
            assert not task_manager._is_running

    @pytest.mark.asyncio
    async def test_start_already_running(self, task_manager):
        """Test starting task manager when already running."""
        with patch(
            "app.infrastructure.taskiq.task_manager.TaskAutodiscovery"
        ) as mock_autodiscovery:
            mock_autodiscovery.return_value.discover_and_register_tasks = Mock()

            await task_manager.start()
            await task_manager.start()  # Should not raise error

            await task_manager.stop()

    @pytest.mark.asyncio
    async def test_submit_task_success(
        self, task_manager, mock_broker, mock_di_container
    ):
        """Test successful task submission."""
        with patch("app.infrastructure.taskiq.task_manager.di", mock_di_container):
            await task_manager.start()

            # Setup mock task function
            mock_task_func = AsyncMock()
            mock_task_result = Mock()
            mock_task_result.task_id = "test-task-123"
            mock_task_func.kiq.return_value = mock_task_result
            mock_task_func.labels = {"priority": "high"}

            mock_broker.local_task_registry["test_task"] = mock_task_func

            task_id = await task_manager.submit_task(
                "test_task", "arg1", param1="value1"
            )

            assert task_id == "test-task-123"
            assert task_id in task_manager.task_registry

            task_info = task_manager.task_registry[task_id]
            assert task_info.task_name == "test_task"
            assert task_info.status == TaskStatus.PENDING
            assert task_info.priority == TaskPriority.HIGH
            assert task_info.metadata["args"] == ("arg1",)
            assert task_info.metadata["kwargs"]["param1"] == "value1"

            await task_manager.stop()

    @pytest.mark.asyncio
    async def test_submit_task_not_running(self, task_manager):
        """Test task submission when manager is not running."""
        with pytest.raises(TaskManagerError, match="task manager is not running"):
            await task_manager.submit_task("test_task")

    @pytest.mark.asyncio
    async def test_submit_task_not_found(self, task_manager):
        """Test task submission when task not found."""
        await task_manager.start()

        with pytest.raises(
            TaskNotFoundError, match="task test_task not found in broker"
        ):
            await task_manager.submit_task("test_task")

        await task_manager.stop()

    @pytest.mark.asyncio
    async def test_submit_task_failure(
        self, task_manager, mock_broker, mock_di_container
    ):
        """Test task submission failure."""
        with patch("app.infrastructure.taskiq.task_manager.di", mock_di_container):
            await task_manager.start()

            # Setup mock task function that raises exception
            mock_task_func = AsyncMock()
            mock_task_func.kiq.side_effect = Exception("Submission failed")
            mock_task_func.labels = {}

            mock_broker.local_task_registry["test_task"] = mock_task_func

            with pytest.raises(
                TaskSubmissionError, match="failed to submit task test_task"
            ):
                await task_manager.submit_task("test_task")

            await task_manager.stop()

    @pytest.mark.asyncio
    async def test_get_task_status_not_found(self, task_manager):
        """Test getting status of non-existent task."""
        result = await task_manager.get_task_status("non-existent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_task_status_terminal_state(self, task_manager, sample_task_info):
        """Test getting status of task in terminal state."""
        sample_task_info.status = TaskStatus.SUCCESS
        task_manager.task_registry[sample_task_info.task_id] = sample_task_info

        result = await task_manager.get_task_status(sample_task_info.task_id)
        assert result == sample_task_info

    @pytest.mark.asyncio
    async def test_get_task_status_with_result_backend(
        self, task_manager, mock_broker, sample_task_info, mock_di_container
    ):
        """Test getting task status with result backend."""
        with patch("app.infrastructure.taskiq.task_manager.di", mock_di_container):
            task_manager.task_registry[sample_task_info.task_id] = sample_task_info

            # Mock successful result
            mock_result = Mock()
            mock_result.is_err = False
            mock_result.return_value = {"success": True}
            mock_broker.result_backend.get_result.return_value = mock_result

            result = await task_manager.get_task_status(sample_task_info.task_id)

            assert result.status == TaskStatus.SUCCESS
            assert result.result == {"success": True}

    @pytest.mark.asyncio
    async def test_cancel_task_success(
        self, task_manager, sample_task_info, mock_di_container
    ):
        """Test successful task cancellation."""
        with patch("app.infrastructure.taskiq.task_manager.di", mock_di_container):
            # Setup async mock for broker's cancel_task
            task_manager.broker.cancel_task = AsyncMock(return_value=True)

            task_manager.task_registry[sample_task_info.task_id] = sample_task_info

            result = await task_manager.cancel_task(sample_task_info.task_id)

            assert result is True
            assert sample_task_info.status == TaskStatus.CANCELLED
            assert sample_task_info.completed_at is not None

            # Verify async method was awaited
            task_manager.broker.cancel_task.assert_awaited_once_with(
                sample_task_info.task_id
            )

    @pytest.mark.asyncio
    async def test_cancel_task_not_found(self, task_manager):
        """Test cancelling non-existent task."""
        result = await task_manager.cancel_task("non-existent")
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_task_wrong_status(self, task_manager, sample_task_info):
        """Test cancelling task in wrong status."""
        sample_task_info.status = TaskStatus.SUCCESS
        task_manager.task_registry[sample_task_info.task_id] = sample_task_info

        result = await task_manager.cancel_task(sample_task_info.task_id)
        assert result is False

    @pytest.mark.asyncio
    async def test_get_tasks_by_status(self, task_manager, mock_di_container):
        """Test getting tasks by status."""
        with patch("app.infrastructure.taskiq.task_manager.di", mock_di_container):
            pending_task = TaskInfo(
                task_id="pending-1",
                task_name="test_task",
                status=TaskStatus.PENDING,
                created_at=datetime.now(UTC),
            )
            success_task = TaskInfo(
                task_id="success-1",
                task_name="test_task",
                status=TaskStatus.SUCCESS,
                created_at=datetime.now(UTC),
            )

            task_manager.task_registry["pending-1"] = pending_task
            task_manager.task_registry["success-1"] = success_task

            pending_tasks = await task_manager.get_tasks_by_status(TaskStatus.PENDING)
            success_tasks = await task_manager.get_tasks_by_status(TaskStatus.SUCCESS)

            assert len(pending_tasks) == 1
            assert len(success_tasks) == 1
            assert pending_tasks[0].task_id == "pending-1"
            assert success_tasks[0].task_id == "success-1"

    @pytest.mark.asyncio
    async def test_get_tasks_by_name(self, task_manager, mock_di_container):
        """Test getting tasks by name."""
        with patch("app.infrastructure.taskiq.task_manager.di", mock_di_container):
            task_a = TaskInfo(
                task_id="task-a-1",
                task_name="task_a",
                status=TaskStatus.PENDING,
                created_at=datetime.now(UTC),
            )
            task_b = TaskInfo(
                task_id="task-b-1",
                task_name="task_b",
                status=TaskStatus.PENDING,
                created_at=datetime.now(UTC),
            )

            task_manager.task_registry["task-a-1"] = task_a
            task_manager.task_registry["task-b-1"] = task_b

            tasks_a = await task_manager.get_tasks_by_name("task_a")
            tasks_b = await task_manager.get_tasks_by_name("task_b")

            assert len(tasks_a) == 1
            assert len(tasks_b) == 1
            assert tasks_a[0].task_id == "task-a-1"
            assert tasks_b[0].task_id == "task-b-1"

    @pytest.mark.asyncio
    async def test_health_check(self, task_manager):
        """Test health check functionality."""
        health = await task_manager.health_check()
        assert health["is_running"] is False
        assert health["cleanup_task_running"] is False

        with patch(
            "app.infrastructure.taskiq.task_manager.TaskAutodiscovery"
        ) as mock_autodiscovery:
            mock_autodiscovery.return_value.discover_and_register_tasks = Mock()

            await task_manager.start()
            health = await task_manager.health_check()
            assert health["is_running"] is True
            assert health["cleanup_task_running"] is True
            assert health["registry_size"] == 0
            assert health["registry_limit"] == 5

            await task_manager.stop()

    @pytest.mark.asyncio
    async def test_registry_size_limiting_fixed_bug(
        self, task_manager, mock_di_container
    ):
        """Test registry size limiting with the fixed sorting bug."""
        with patch("app.infrastructure.taskiq.task_manager.di", mock_di_container):
            await task_manager.start()

            # Add more tasks than the limit (5)
            for i in range(7):
                task_info = TaskInfo(
                    task_id=f"task-{i}",
                    task_name="test_task",
                    status=TaskStatus.SUCCESS if i < 4 else TaskStatus.PENDING,
                    created_at=datetime.now(UTC) - timedelta(seconds=i),
                )
                task_manager.task_registry[f"task-{i}"] = task_info

            # Trigger size limiting
            task_manager._limit_registry_size()

            # Registry should be limited to max size
            assert len(task_manager.task_registry) <= task_manager.max_registry_size

            await task_manager.stop()

    @pytest.mark.asyncio
    async def test_get_task_statistics_empty(self, task_manager):
        """Test statistics with empty registry."""
        stats = await task_manager.get_task_statistics()

        assert stats["total_tasks"] == 0
        assert stats["success_rate"] == 0
        assert stats["avg_execution_time"] == 0
        assert all(count == 0 for count in stats["status_counts"].values())

    @pytest.mark.asyncio
    async def test_get_task_statistics_with_data(self, task_manager, mock_di_container):
        """Test statistics with task data."""
        with patch("app.infrastructure.taskiq.task_manager.di", mock_di_container):
            current_time = datetime.now(UTC)

            # Add completed task with timing
            task_info = TaskInfo(
                task_id="completed-task-1",
                task_name="test_task",
                status=TaskStatus.SUCCESS,
                created_at=current_time - timedelta(minutes=5),
                started_at=current_time - timedelta(minutes=2),
                completed_at=current_time,
                priority=TaskPriority.HIGH,
            )
            task_manager.task_registry["completed-task-1"] = task_info

            # Add pending task
            pending_task = TaskInfo(
                task_id="pending-task-1",
                task_name="another_task",
                status=TaskStatus.PENDING,
                created_at=current_time,
                priority=TaskPriority.LOW,
            )
            task_manager.task_registry["pending-task-1"] = pending_task

            stats = await task_manager.get_task_statistics()

            assert stats["total_tasks"] == 2
            assert stats["success_rate"] == 50.0
            assert stats["avg_execution_time"] > 0
            assert stats["status_counts"]["success"] == 1
            assert stats["status_counts"]["pending"] == 1
            assert stats["priority_counts"]["high"] == 1
            assert stats["priority_counts"]["low"] == 1
            assert "test_task" in stats["task_statistics"]
            assert "another_task" in stats["task_statistics"]

    @pytest.mark.asyncio
    async def test_cleanup_old_tasks(self, task_manager, mock_di_container):
        """Test cleanup of old tasks."""
        with patch("app.infrastructure.taskiq.task_manager.di", mock_di_container):
            current_time = datetime.now(UTC)

            # Add old completed task
            old_task = TaskInfo(
                task_id="old-task",
                task_name="test_task",
                status=TaskStatus.SUCCESS,
                created_at=current_time - timedelta(days=10),
                completed_at=current_time - timedelta(days=10),
            )
            task_manager.task_registry["old-task"] = old_task

            # Add recent task
            recent_task = TaskInfo(
                task_id="recent-task",
                task_name="test_task",
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
