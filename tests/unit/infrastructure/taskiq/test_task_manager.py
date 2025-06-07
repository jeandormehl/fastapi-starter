from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.core.errors.errors import ApplicationError, ErrorCode
from app.infrastructure.taskiq.schemas import TaskPriority, TaskStatus
from app.infrastructure.taskiq.task_manager import (
    TaskInfo,
    TaskManager,
    TaskManagerError,
    TaskSubmissionError,
)


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
        return TaskManager(mock_broker, max_registry_size=5)  # Small size for testing

    @pytest.mark.asyncio
    async def test_submit_task_success(
        self, task_manager, mock_broker, mock_di_container
    ):
        """Test successful task submission."""
        await task_manager.start()

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
            assert task_id in task_manager.task_registry

            task_info = task_manager.task_registry[task_id]
            assert task_info.task_name == "test_task"
            assert task_info.status == TaskStatus.PENDING
            assert task_info.priority == TaskPriority.HIGH
            assert task_info.metadata["args"] == ("arg1", "arg2")
            assert task_info.metadata["kwargs"]["param1"] == "value1"

        await task_manager.stop()

    @pytest.mark.asyncio
    async def test_submit_task_not_running(self, task_manager):
        """Test task submission when manager is not running."""
        with pytest.raises(TaskManagerError, match="task manager is not running"):
            await task_manager.submit_task("test_task")

    @pytest.mark.asyncio
    async def test_submit_task_invalid_delay(self, task_manager, mock_broker):
        """Test task submission with invalid delay."""
        await task_manager.start()
        mock_broker.test_task = AsyncMock()

        with pytest.raises(ValueError, match="delay must be non-negative"):
            await task_manager.submit_task("test_task", delay=-1)

        await task_manager.stop()

    @pytest.mark.asyncio
    async def test_submit_task_invalid_eta(
        self, task_manager, mock_broker, mock_di_container
    ):
        """Test task submission with invalid ETA."""
        await task_manager.start()
        mock_broker.test_task = AsyncMock()

        with patch("app.infrastructure.taskiq.task_manager.di", mock_di_container):
            past_eta = datetime.now(mock_di_container["timezone"]) - timedelta(hours=1)

            with pytest.raises(ValueError, match="eta must be in the future"):
                await task_manager.submit_task("test_task", eta=past_eta)

        await task_manager.stop()

    @pytest.mark.asyncio
    async def test_submit_task_timeout(self, task_manager, mock_broker):
        """Test task submission timeout."""
        await task_manager.start()

        # Mock task function that times out
        mock_task_func = AsyncMock()
        mock_task_func.kiq.side_effect = TimeoutError()
        mock_broker.test_task = mock_task_func

        with pytest.raises(TaskSubmissionError, match="task submission timeout"):
            await task_manager.submit_task("test_task")

        await task_manager.stop()

    @pytest.mark.asyncio
    async def test_get_task_status_with_result_backend_timeout(
        self, task_manager, mock_broker, mock_di_container
    ):
        """Test getting task status with result backend timeout."""
        await task_manager.start()

        with patch("app.infrastructure.taskiq.task_manager.di", mock_di_container):
            task_id = "test-task-123"
            task_info = TaskInfo(
                task_id=task_id,
                task_name="test_task",
                status=TaskStatus.RUNNING,
                created_at=datetime.now(mock_di_container["timezone"]),
            )
            task_manager.task_registry[task_id] = task_info

            # Mock timeout
            mock_broker.result_backend.get_result.side_effect = TimeoutError()

            result = await task_manager.get_task_status(task_id)
            assert (
                result.status == TaskStatus.RUNNING
            )  # Status unchanged due to timeout

        await task_manager.stop()

    @pytest.mark.asyncio
    async def test_cancel_task_not_cancellable(self, task_manager, mock_di_container):
        """Test cancelling task in non-cancellable state."""
        await task_manager.start()

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

        await task_manager.stop()

    @pytest.mark.asyncio
    async def test_retry_failed_task_max_retries_exceeded(
        self, task_manager, mock_di_container
    ):
        """Test retry when max retries exceeded."""
        await task_manager.start()

        with patch("app.infrastructure.taskiq.task_manager.di", mock_di_container):
            task_id = "failed-task-123"
            task_info = TaskInfo(
                task_id=task_id,
                task_name="test_task",
                status=TaskStatus.FAILED,
                created_at=datetime.now(mock_di_container["timezone"]),
                retry_count=6,  # Exceeds max of 5
                metadata={"args": (), "kwargs": {}},
            )
            task_manager.task_registry[task_id] = task_info

            result = await task_manager.retry_failed_task(task_id)
            assert result is None

        await task_manager.stop()

    @pytest.mark.asyncio
    async def test_retry_failed_task_force(
        self, task_manager, mock_broker, mock_di_container
    ):
        """Test force retry of non-failed task."""
        await task_manager.start()

        with patch("app.infrastructure.taskiq.task_manager.di", mock_di_container):
            task_id = "success-task-123"
            task_info = TaskInfo(
                task_id=task_id,
                task_name="test_task",
                status=TaskStatus.SUCCESS,
                created_at=datetime.now(mock_di_container["timezone"]),
                metadata={"args": ("arg1",), "kwargs": {"param1": "value1"}},
            )
            task_manager.task_registry[task_id] = task_info

            # Setup mock for new task submission
            mock_task_func = AsyncMock()
            mock_task_result = Mock()
            mock_task_result.task_id = "retry-task-456"
            mock_task_func.kiq.return_value = mock_task_result
            mock_broker.test_task = mock_task_func

            new_task_id = await task_manager.retry_failed_task(task_id, force=True)
            assert new_task_id == "retry-task-456"

        await task_manager.stop()

    @pytest.mark.asyncio
    async def test_registry_size_limiting_fixed_bug(
        self, task_manager, mock_broker, mock_di_container
    ):
        """Test registry size limiting with the fixed sorting bug."""
        await task_manager.start()

        with patch("app.infrastructure.taskiq.task_manager.di", mock_di_container):
            # Setup mock task function
            mock_task_func = AsyncMock()
            mock_broker.test_task = mock_task_func

            # Submit more tasks than the limit (5)
            task_ids = []
            for i in range(7):
                mock_task_result = Mock()
                mock_task_result.task_id = f"task-{i}"
                mock_task_func.kiq.return_value = mock_task_result

                task_id = await task_manager.submit_task("test_task", f"arg{i}")
                task_ids.append(task_id)

            # Registry should be limited to max size
            assert len(task_manager.task_registry) <= task_manager.max_registry_size

        await task_manager.stop()

    @pytest.mark.asyncio
    async def test_get_tasks_by_status(self, task_manager, mock_di_container):
        """Test getting tasks by status."""
        await task_manager.start()

        with patch("app.infrastructure.taskiq.task_manager.di", mock_di_container):
            # Add tasks with different statuses
            pending_task = TaskInfo(
                task_id="pending-1",
                task_name="test_task",
                status=TaskStatus.PENDING,
                created_at=datetime.now(mock_di_container["timezone"]),
            )
            success_task = TaskInfo(
                task_id="success-1",
                task_name="test_task",
                status=TaskStatus.SUCCESS,
                created_at=datetime.now(mock_di_container["timezone"]),
            )

            task_manager.task_registry["pending-1"] = pending_task
            task_manager.task_registry["success-1"] = success_task

            pending_tasks = await task_manager.get_tasks_by_status(TaskStatus.PENDING)
            success_tasks = await task_manager.get_tasks_by_status(TaskStatus.SUCCESS)

            assert len(pending_tasks) == 1
            assert len(success_tasks) == 1
            assert pending_tasks[0].task_id == "pending-1"
            assert success_tasks[0].task_id == "success-1"

        await task_manager.stop()

    @pytest.mark.asyncio
    async def test_get_tasks_by_name(self, task_manager, mock_di_container):
        """Test getting tasks by name."""
        await task_manager.start()

        with patch("app.infrastructure.taskiq.task_manager.di", mock_di_container):
            # Add tasks with different names
            task_a = TaskInfo(
                task_id="task-a-1",
                task_name="task_a",
                status=TaskStatus.PENDING,
                created_at=datetime.now(mock_di_container["timezone"]),
            )
            task_b = TaskInfo(
                task_id="task-b-1",
                task_name="task_b",
                status=TaskStatus.PENDING,
                created_at=datetime.now(mock_di_container["timezone"]),
            )

            task_manager.task_registry["task-a-1"] = task_a
            task_manager.task_registry["task-b-1"] = task_b

            tasks_a = await task_manager.get_tasks_by_name("task_a")
            tasks_b = await task_manager.get_tasks_by_name("task_b")

            assert len(tasks_a) == 1
            assert len(tasks_b) == 1
            assert tasks_a[0].task_id == "task-a-1"
            assert tasks_b[0].task_id == "task-b-1"

        await task_manager.stop()

    @pytest.mark.asyncio
    async def test_health_check(self, task_manager):
        """Test health check functionality."""
        # Before starting
        health = await task_manager.health_check()
        assert health["is_running"] is False
        assert health["cleanup_task_running"] is False

        # After starting
        await task_manager.start()
        health = await task_manager.health_check()
        assert health["is_running"] is True
        assert health["cleanup_task_running"] is True
        assert health["registry_size"] == 0
        assert health["registry_limit"] == 5

        await task_manager.stop()

    @pytest.mark.asyncio
    async def test_cleanup_error_handling(self, task_manager):
        """Test cleanup loop error handling."""
        await task_manager.start()

        # Mock cleanup to raise exception
        with (
            patch.object(
                task_manager,
                "_cleanup_old_tasks",
                side_effect=ApplicationError(
                    ErrorCode.EXTERNAL_SERVICE_TIMEOUT, "Cleanup error"
                ),
            ),
            pytest.raises(ApplicationError),
        ):
            await task_manager._cleanup_old_tasks()

        await task_manager.stop()

    @pytest.mark.asyncio
    async def test_empty_statistics(self, task_manager):
        """Test statistics with empty registry."""
        await task_manager.start()

        stats = await task_manager.get_task_statistics()

        assert stats["total_tasks"] == 0
        assert stats["success_rate"] == 0
        assert stats["avg_execution_time"] == 0
        assert all(count == 0 for count in stats["status_counts"].values())

        await task_manager.stop()

    @pytest.mark.asyncio
    async def test_performance_metrics_in_statistics(
        self, task_manager, mock_di_container
    ):
        """Test performance metrics in statistics."""
        await task_manager.start()

        with patch("app.infrastructure.taskiq.task_manager.di", mock_di_container):
            # Add a completed task with timing
            current_time = datetime.now(mock_di_container["timezone"])
            task_info = TaskInfo(
                task_id="perf-task-1",
                task_name="perf_task",
                status=TaskStatus.SUCCESS,
                created_at=current_time - timedelta(minutes=5),
                started_at=current_time - timedelta(minutes=2),
                completed_at=current_time,
            )
            task_manager.task_registry["perf-task-1"] = task_info

            stats = await task_manager.get_task_statistics()

            assert stats["total_tasks"] == 1
            assert stats["success_rate"] == 100.0
            assert stats["avg_execution_time"] > 0
            assert stats["performance_metrics"]["completed_tasks"] == 1

        await task_manager.stop()
