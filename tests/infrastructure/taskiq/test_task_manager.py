from unittest.mock import AsyncMock, Mock, patch

from taskiq import AsyncBroker

from app.infrastructure.taskiq.config import TaskiqConfiguration
from app.infrastructure.taskiq.task_manager import TaskManager


class TestTaskManager:
    """Test task manager functionality."""

    async def test_task_manager_initialization(self, mock_broker: AsyncBroker):
        """Test task manager initialization."""
        with patch("app.common.logging.initialize_logging"):
            manager = TaskManager(mock_broker)
            assert manager is not None

    async def test_task_manager_send_task(self, task_manager: TaskManager):
        """Test sending task through task manager."""
        with patch.object(
            task_manager, "submit_task", new_callable=AsyncMock
        ) as mock_send:
            mock_send.return_value = Mock(task_id="test-task-123")

            result = await task_manager.submit_task("test_task", arg1="value1")

            assert result.task_id == "test-task-123"
            mock_send.assert_called_once_with("test_task", arg1="value1")

    async def test_task_manager_get_result(self, task_manager: TaskManager):
        """Test getting task result through task manager."""
        with patch.object(
            task_manager, "get_task_status", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = {"status": "completed", "result": "success"}

            result = await task_manager.get_task_status("test-task-123")

            assert result["status"] == "completed"
            mock_get.assert_called_once_with("test-task-123")

    def test_taskiq_configuration(self, taskiq_config: TaskiqConfiguration):
        """Test Taskiq configuration."""
        assert taskiq_config.broker_type == "memory"
        assert taskiq_config.default_queue == "test_queue"
        assert taskiq_config.default_retry_count == 0
        assert not taskiq_config.enable_metrics
