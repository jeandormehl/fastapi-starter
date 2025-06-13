import asyncio
import contextlib
from datetime import datetime, timedelta
from typing import Any

from kink import di
from taskiq import AsyncBroker

from app.common.constants import APP_PATH, ROOT_PATH
from app.common.logging import get_logger
from app.infrastructure.taskiq.schemas import TaskInfo, TaskPriority, TaskStatus
from app.infrastructure.taskiq.utils import TaskAutodiscovery


class TaskManagerError(Exception):
    """Base exception for TaskManager errors."""


class TaskNotFoundError(TaskManagerError):
    """Raised when a task is not found."""


class TaskSubmissionError(TaskManagerError):
    """Raised when task submission fails."""


class TaskManager:
    """Task monitoring and management with simplified architecture."""

    def __init__(self, broker: AsyncBroker, max_registry_size: int = 10000) -> None:
        self.broker = broker
        self.logger = get_logger(__name__)
        self.task_registry: dict[str, TaskInfo] = {}
        self.cleanup_interval = 3600  # 1 hour
        self.max_registry_size = max_registry_size
        self._cleanup_task: asyncio.Task | None = None
        self._is_running = False

    async def start(self) -> None:
        """Start task manager with autodiscovery."""
        if self._is_running:
            self.logger.warning("task manager is already running")
            return

        try:
            # Run autodiscovery BEFORE starting cleanup task
            auto_discovery = TaskAutodiscovery(self.broker, APP_PATH, ROOT_PATH)
            auto_discovery.discover_and_register_tasks()

            # Start cleanup task
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

            self._is_running = True
            self.logger.info("task manager started successfully")

        except Exception as e:
            self.logger.error(f"failed to start task manager: {e}")
            raise

    async def stop(self) -> None:
        """Stop task manager with proper cleanup."""

        if not self._is_running:
            self.logger.warning("task manager is not running")
            return

        self._is_running = False

        if self._cleanup_task:
            self._cleanup_task.cancel()

            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task

        self.logger.info("task manager stopped successfully")

    async def submit_task(self, task_name: str, *args: Any, **kwargs: Any) -> str:
        """Submit task using Taskiq's built-in functionality."""

        if not self._is_running:
            msg = "task manager is not running"
            raise TaskManagerError(msg)

        # Get task function from broker registry
        task_func = self.broker.local_task_registry.get(task_name)

        if not task_func:
            msg = f"task {task_name} not found in broker"
            raise TaskNotFoundError(msg)

        try:
            # Submit task using Taskiq's kiq method
            task_result = await task_func.kiq(*args, **kwargs)
            task_id = task_result.task_id

            # Register task for monitoring
            task_labels = task_func.labels or {}
            task_info = TaskInfo(
                task_id=task_id,
                task_name=task_name,
                status=TaskStatus.PENDING,
                created_at=datetime.now(di["timezone"]),
                priority=task_labels.get(
                    "priority", TaskPriority.NORMAL.to_taskiq_priority()
                ),
                metadata={
                    "args": args,
                    "kwargs": kwargs,
                    "labels": task_labels,
                    "submitted_at": datetime.now(di["timezone"]).isoformat(),
                },
            )

            self.task_registry[task_id] = task_info
            self._limit_registry_size()

            self.logger.info(
                f"task submitted successfully: {task_name}",
                extra={"task_id": task_id, "labels": task_labels},
            )

            return task_id

        except Exception as e:
            error_msg = f"failed to submit task {task_name}: {e}"
            self.logger.error(error_msg, exc_info=True)

            raise TaskSubmissionError(error_msg) from e

    async def get_task_status(self, task_id: str) -> TaskInfo | None:
        """Get task status with result backend integration."""

        task_info = self.task_registry.get(task_id)
        if not task_info:
            return None

        # Skip result backend check for terminal states
        if task_info.status in [
            TaskStatus.SUCCESS,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        ]:
            return task_info

        # Try to get updated status from result backend
        try:
            if hasattr(self.broker, "result_backend") and self.broker.result_backend:
                result = await asyncio.wait_for(
                    self.broker.result_backend.get_result(task_id), timeout=5.0
                )

                if result:
                    task_info.status = (
                        TaskStatus.SUCCESS if not result.is_err else TaskStatus.FAILED
                    )
                    task_info.completed_at = datetime.now(di["timezone"])
                    task_info.result = result.return_value

        except (TimeoutError, Exception) as e:
            self.logger.debug(f"could not fetch result for task {task_id}: {e}")

        return task_info

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a task if supported by the broker."""

        task_info = self.task_registry.get(task_id)
        if not task_info:
            self.logger.warning(f"attempted to cancel non-existent task: {task_id}")
            return False

        if task_info.status not in [TaskStatus.PENDING, TaskStatus.RUNNING]:
            self.logger.info(
                f"cannot cancel task {task_id} with status {task_info.status}"
            )
            return False

        try:
            # Try broker-specific cancellation if available
            if hasattr(self.broker, "cancel_task"):
                await self.broker.cancel_task(task_id)

            task_info.status = TaskStatus.CANCELLED
            task_info.completed_at = datetime.now(di["timezone"])
            task_info.metadata["cancelled_at"] = task_info.completed_at.isoformat()

            self.logger.info(f"task cancelled successfully: {task_id}")
            return True

        except Exception as e:
            self.logger.error(f"failed to cancel task {task_id}: {e}", exc_info=True)
            return False

    async def _cleanup_loop(self) -> None:
        """Background cleanup with error handling."""

        consecutive_errors = 0
        max_consecutive_errors = 5

        while self._is_running:
            try:
                await asyncio.sleep(self.cleanup_interval)
                if not self._is_running:
                    break

                await self._cleanup_old_tasks()
                consecutive_errors = 0

            except asyncio.CancelledError:
                self.logger.info("cleanup loop cancelled")
                break

            except Exception as e:
                consecutive_errors += 1
                self.logger.error(
                    f"error in cleanup loop (attempt {consecutive_errors}): {e}",
                    exc_info=True,
                )

                if consecutive_errors >= max_consecutive_errors:
                    self.logger.critical(
                        "too many consecutive cleanup errors, stopping cleanup"
                    )
                    break

                await asyncio.sleep(min(60 * consecutive_errors, 300))

    async def _cleanup_old_tasks(self) -> None:
        """Clean up old completed task records."""

        try:
            cutoff_time = datetime.now(di["timezone"]) - timedelta(days=7)

            old_task_ids = [
                task_id
                for task_id, task_info in self.task_registry.items()
                if (
                    task_info.completed_at
                    and task_info.completed_at < cutoff_time
                    and task_info.status
                    in [TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED]
                )
            ]

            for task_id in old_task_ids:
                self.task_registry.pop(task_id, None)

            if old_task_ids:
                self.logger.info(f"cleaned up {len(old_task_ids)} old task records")

        except Exception as e:
            self.logger.error(f"failed to cleanup old tasks: {e}", exc_info=True)
            raise

    def _limit_registry_size(self) -> None:
        """Limit registry size with proper sorting."""

        if len(self.task_registry) <= self.max_registry_size:
            return

        try:
            sorted_tasks = sorted(
                self.task_registry.items(),
                key=lambda item: item[1].created_at,
            )

            tasks_to_remove = len(self.task_registry) - self.max_registry_size
            removed_count = 0

            # Prefer removing completed tasks over active ones
            for task_id, task_info in sorted_tasks:
                if removed_count >= tasks_to_remove:
                    break

                if task_info.status in [
                    TaskStatus.SUCCESS,
                    TaskStatus.FAILED,
                    TaskStatus.CANCELLED,
                ]:
                    del self.task_registry[task_id]
                    removed_count += 1

            # Remove remaining tasks if needed
            if removed_count < tasks_to_remove:
                remaining_to_remove = tasks_to_remove - removed_count
                # noinspection PyPep8
                for task_id, _ in sorted_tasks[
                    removed_count : removed_count + remaining_to_remove
                ]:
                    if task_id in self.task_registry:
                        del self.task_registry[task_id]
                        removed_count += 1

            if removed_count > 0:
                self.logger.info(
                    f"removed {removed_count} tasks due to registry size limit"
                )

        except Exception as e:
            self.logger.error(f"failed to limit registry size: {e}", exc_info=True)

    async def get_tasks_by_status(self, status: TaskStatus) -> list[TaskInfo]:
        """Get all tasks with a specific status."""

        return [
            task_info
            for task_info in self.task_registry.values()
            if task_info.status == status
        ]

    async def get_tasks_by_name(self, task_name: str) -> list[TaskInfo]:
        """Get all tasks with a specific name."""

        return [
            task_info
            for task_info in self.task_registry.values()
            if task_info.task_name == task_name
        ]

    async def health_check(self) -> dict[str, Any]:
        """Basic health check for task manager status."""

        try:
            broker_health = await self._check_broker_health()

            return {
                "is_running": self._is_running,
                "cleanup_task_running": self._cleanup_task is not None
                and not self._cleanup_task.done(),
                "registry_size": len(self.task_registry),
                "registry_limit": self.max_registry_size,
                "broker_health": broker_health,
                "last_check": datetime.now(di["timezone"]).isoformat(),
            }

        except Exception as e:
            return {
                "is_running": False,
                "error": str(e),
                "status": "unhealthy",
                "last_check": datetime.now(di["timezone"]).isoformat(),
            }

    async def _check_broker_health(self) -> dict[str, Any]:
        """Check the health of the TaskIQ broker"""

        try:
            if hasattr(self.broker, "ping"):
                await self.broker.ping()

                return {"status": "healthy", "connected": True}
            # For brokers without ping, check if they're properly initialized
            return {
                "status": "healthy" if self.broker else "unhealthy",
                "connected": self.broker is not None,
            }

        except Exception as e:
            return {"status": "unhealthy", "connected": False, "error": str(e)}
