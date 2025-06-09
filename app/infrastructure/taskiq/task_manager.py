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
            # Start cleanup task
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

            # Run autodiscovery to register tasks
            auto_discovery = TaskAutodiscovery(self.broker, APP_PATH, ROOT_PATH)
            auto_discovery.discover_and_register_tasks()

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
                priority=TaskPriority(
                    task_labels.get("priority", TaskPriority.NORMAL.value)
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

    # noinspection PyUnresolvedReferences
    async def get_task_statistics(self) -> dict[str, Any]:
        """Get comprehensive task statistics."""

        if not self.task_registry:
            return self._empty_statistics()

        now = datetime.now(di["timezone"])
        last_hour = now - timedelta(hours=1)
        last_day = now - timedelta(days=1)

        # Initialize counters
        status_counts = dict.fromkeys(TaskStatus, 0)
        priority_counts = dict.fromkeys(TaskPriority, 0)
        hour_stats = dict.fromkeys(TaskStatus, 0)
        day_stats = dict.fromkeys(TaskStatus, 0)
        task_name_stats = {}

        total_duration = 0
        completed_tasks = 0

        for task_info in self.task_registry.values():
            status_counts[task_info.status] += 1
            priority_counts[task_info.priority] += 1

            if task_info.created_at >= last_hour:
                hour_stats[task_info.status] += 1
            if task_info.created_at >= last_day:
                day_stats[task_info.status] += 1

            # Task name statistics
            task_name = task_info.task_name
            if task_name not in task_name_stats:
                task_name_stats[task_name] = {
                    "total": 0,
                    "success": 0,
                    "failed": 0,
                    "avg_duration": 0.0,
                }

            stats = task_name_stats[task_name]
            stats["total"] += 1

            if task_info.status == TaskStatus.SUCCESS:
                stats["success"] += 1
            elif task_info.status == TaskStatus.FAILED:
                stats["failed"] += 1

            # Calculate duration if completed
            if (
                task_info.completed_at
                and task_info.started_at
                and task_info.status in [TaskStatus.SUCCESS, TaskStatus.FAILED]
            ):
                duration = (
                    task_info.completed_at - task_info.started_at
                ).total_seconds()
                total_duration += duration
                completed_tasks += 1

        # Calculate success rate
        total_tasks = len(self.task_registry)
        success_rate = (
            (status_counts[TaskStatus.SUCCESS] / total_tasks * 100)
            if total_tasks > 0
            else 0
        )

        return {
            "total_tasks": total_tasks,
            "registry_size_limit": self.max_registry_size,
            "registry_utilization": (
                f"{(total_tasks / self.max_registry_size * 100):.1f}%"
            ),
            "status_counts": {
                status.value: count for status, count in status_counts.items()
            },
            "priority_counts": {
                priority.value: count for priority, count in priority_counts.items()
            },
            "last_hour": {status.value: count for status, count in hour_stats.items()},
            "last_day": {status.value: count for status, count in day_stats.items()},
            "task_statistics": task_name_stats,
            "success_rate": round(success_rate, 2),
            "avg_execution_time": round(total_duration / completed_tasks, 4)
            if completed_tasks > 0
            else 0,
            "performance_metrics": {
                "completed_tasks": completed_tasks,
                "pending_tasks": status_counts[TaskStatus.PENDING],
                "running_tasks": status_counts[TaskStatus.RUNNING],
            },
        }

    def _empty_statistics(self) -> dict[str, Any]:
        """Return empty statistics structure."""

        return {
            "total_tasks": 0,
            "registry_size_limit": self.max_registry_size,
            "registry_utilization": "0.0%",
            "status_counts": {status.value: 0 for status in TaskStatus},
            "priority_counts": {priority.value: 0 for priority in TaskPriority},
            "last_hour": {status.value: 0 for status in TaskStatus},
            "last_day": {status.value: 0 for status in TaskStatus},
            "task_statistics": {},
            "success_rate": 0,
            "avg_execution_time": 0,
            "performance_metrics": {
                "completed_tasks": 0,
                "pending_tasks": 0,
                "running_tasks": 0,
            },
        }

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
        """Limit registry size with proper sorting - FIXED BUG."""

        if len(self.task_registry) <= self.max_registry_size:
            return

        try:
            # FIXED: Properly access created_at from TaskInfo object

            sorted_tasks = sorted(
                self.task_registry.items(),
                key=lambda item: item[1].created_at,  # item[1] is the TaskInfo object
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
        """Perform health check on task manager."""

        return {
            "is_running": self._is_running,
            "registry_size": len(self.task_registry),
            "registry_limit": self.max_registry_size,
            "cleanup_task_running": self._cleanup_task is not None
            and not self._cleanup_task.done(),
            "broker_connected": hasattr(self.broker, "is_connected")
            and getattr(self.broker, "is_connected", lambda: True)(),
        }
