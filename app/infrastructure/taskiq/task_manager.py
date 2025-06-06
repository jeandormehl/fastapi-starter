import asyncio
import contextlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from kink import di
from taskiq import AsyncBroker

from app.core.logging import get_logger
from app.infrastructure.taskiq.schemas import TaskPriority, TaskStatus


@dataclass
class TaskInfo:
    """Task information for management."""

    task_id: str
    task_name: str
    status: TaskStatus
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    priority: TaskPriority = TaskPriority.NORMAL
    retry_count: int = 0
    error_message: str | None = None
    result: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class TaskManager:
    """Task management and monitoring."""

    def __init__(self, broker: AsyncBroker) -> None:
        self.broker = broker
        self.logger = get_logger(__name__)
        self.task_registry: dict[str, TaskInfo] = {}
        self.cleanup_interval = 3600  # 1 hour
        self._cleanup_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start task manager."""

        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self.logger.info("task manager started")

    async def stop(self) -> None:
        """Stop task manager."""

        if self._cleanup_task:
            self._cleanup_task.cancel()

            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task

        self.logger.info("task manager stopped")

    async def submit_task(
        self,
        task_name: str,
        *args: Any,
        priority: TaskPriority = TaskPriority.NORMAL,
        delay: int | None = None,
        eta: datetime | None = None,
        **kwargs: Any,
    ) -> str:
        """Submit task with management tracking."""

        # Get task function from broker
        task_func = getattr(self.broker, task_name, None)
        if not task_func:
            msg = f"task {task_name} not found in broker"
            raise ValueError(msg)

        # Prepare task options
        task_options = {
            "priority": priority.value,
            "queue": f"{priority.value}_priority",
        }

        if delay:
            task_options["countdown"] = delay
        if eta:
            task_options["eta"] = eta

        # Submit task
        task_result = await task_func.kiq(*args, **kwargs, **task_options)
        task_id = task_result.task_id

        # Register task
        task_info = TaskInfo(
            task_id=task_id,
            task_name=task_name,
            status=TaskStatus.PENDING,
            created_at=datetime.now(di["timezone"]),
            priority=priority,
            metadata={"args": args, "kwargs": kwargs, "options": task_options},
        )

        self.task_registry[task_id] = task_info

        self._limit_registry_size()

        self.logger.info(
            f"task submitted: {task_name}",
            extra={
                "task_id": task_id,
                "priority": priority.value,
                "delay": delay,
                "eta": eta.isoformat() if eta else None,
            },
        )

        return task_id

    async def get_task_status(self, task_id: str) -> TaskInfo | None:
        """Get task status and information."""

        task_info = self.task_registry.get(task_id)

        if not task_info:
            return None

        # Try to get updated status from broker
        try:
            if hasattr(self.broker, "result_backend"):
                result = await self.broker.result_backend.get_result(task_id)
                if result:
                    task_info.status = (
                        TaskStatus.SUCCESS if not result.is_err else TaskStatus.FAILED
                    )
                    task_info.completed_at = datetime.now(di["timezone"])
                    task_info.result = result.return_value

                    if result.is_err:
                        task_info.error_message = result.log

        except Exception as e:
            self.logger.debug(f"could not fetch result for task {task_id}: {e}")

        return task_info

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a pending task."""

        task_info = self.task_registry.get(task_id)

        if not task_info:
            return False

        if task_info.status not in [TaskStatus.PENDING, TaskStatus.RUNNING]:
            return False

        try:
            # Implementation depends on broker capabilities
            # This is a placeholder for broker-specific cancellation
            task_info.status = TaskStatus.CANCELLED
            task_info.completed_at = datetime.now(di["timezone"])

            self.logger.info(f"task cancelled: {task_id}")

            return True

        except Exception as e:
            self.logger.error(f"failed to cancel task {task_id}: {e}")
            return False

    async def retry_failed_task(self, task_id: str) -> str | None:
        """Retry a failed task."""

        task_info = self.task_registry.get(task_id)

        if not task_info or task_info.status != TaskStatus.FAILED:
            return None

        try:
            # Extract original parameters
            args = task_info.metadata.get("args", ())
            kwargs = task_info.metadata.get("kwargs", {})

            # Submit new task
            new_task_id = await self.submit_task(
                task_info.task_name, *args, priority=task_info.priority, **kwargs
            )

            # Update retry count
            new_task_info = self.task_registry[new_task_id]
            new_task_info.retry_count = task_info.retry_count + 1
            new_task_info.metadata["original_task_id"] = task_id

            self.logger.info(
                f"task retried: {task_info.task_name}",
                extra={
                    "original_task_id": task_id,
                    "new_task_id": new_task_id,
                    "retry_count": new_task_info.retry_count,
                },
            )

            return new_task_id

        except Exception as e:
            self.logger.error(f"failed to retry task {task_id}: {e}")
            return None

    async def get_task_statistics(self) -> dict[str, Any]:
        """Get comprehensive task statistics."""

        now = datetime.now(di["timezone"])

        # Count tasks by status
        status_counts = dict.fromkeys(TaskStatus, 0)
        priority_counts = dict.fromkeys(TaskPriority, 0)

        # Time-based statistics
        last_hour = now - timedelta(hours=1)
        last_day = now - timedelta(days=1)

        hour_stats = dict.fromkeys(TaskStatus, 0)
        day_stats = dict.fromkeys(TaskStatus, 0)

        # Task name statistics
        task_name_stats = {}

        for task_info in self.task_registry.values():
            # Status counts
            status_counts[task_info.status] += 1
            priority_counts[task_info.priority] += 1

            # Time-based counts
            if task_info.created_at >= last_hour:
                hour_stats[task_info.status] += 1
            if task_info.created_at >= last_day:
                day_stats[task_info.status] += 1

            # Task name statistics
            if task_info.task_name not in task_name_stats:
                task_name_stats[task_info.task_name] = {
                    "total": 0,
                    "success": 0,
                    "failed": 0,
                    "avg_duration": 0.0,
                }

            stats = task_name_stats[task_info.task_name]
            stats["total"] += 1

            if task_info.status == TaskStatus.SUCCESS:
                stats["success"] += 1
            elif task_info.status == TaskStatus.FAILED:
                stats["failed"] += 1

            # Calculate duration if completed
            if task_info.completed_at and task_info.started_at:
                duration = (
                    task_info.completed_at - task_info.started_at
                ).total_seconds()
                stats["avg_duration"] = (stats["avg_duration"] + duration) / 2

        # noinspection PyUnresolvedReferences
        return {
            "total_tasks": len(self.task_registry),
            "status_counts": {
                status.value: count for status, count in status_counts.items()
            },
            "priority_counts": {
                priority.value: count for priority, count in priority_counts.items()
            },
            "last_hour": {status.value: count for status, count in hour_stats.items()},
            "last_day": {status.value: count for status, count in day_stats.items()},
            "task_statistics": task_name_stats,
            "success_rate": (
                status_counts[TaskStatus.SUCCESS] / len(self.task_registry) * 100
                if self.task_registry
                else 0
            ),
        }

    async def _cleanup_loop(self) -> None:
        """Background cleanup of old task records."""

        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self._cleanup_old_tasks()

            except asyncio.CancelledError:
                break

            except Exception as e:
                self.logger.error(f"error in cleanup loop: {e}")

    async def _cleanup_old_tasks(self) -> None:
        """Clean up old completed task records."""

        cutoff_time = datetime.now(di["timezone"]) - timedelta(
            days=7
        )  # Keep records for 7 days

        old_task_ids = [
            task_id
            for task_id, task_info in self.task_registry.items()
            if task_info.completed_at and task_info.completed_at < cutoff_time
        ]

        for task_id in old_task_ids:
            del self.task_registry[task_id]

        if old_task_ids:
            self.logger.info(f"cleaned up {len(old_task_ids)} old task records")

    def _limit_registry_size(self, max_size: int = 10000) -> None:
        """Limit the size of the task registry to prevent memory issues."""

        if len(self.task_registry) > max_size:
            # Sort tasks by creation time (oldest first)
            sorted_tasks = sorted(
                self.task_registry.items(), key=lambda item: item[1].created_at
            )

            # Remove oldest tasks to get back under the limit
            tasks_to_remove = len(self.task_registry) - max_size
            for task_id, _ in sorted_tasks[:tasks_to_remove]:
                del self.task_registry[task_id]

            self.logger.info(
                f"removed {tasks_to_remove} old task records due to size limit"
            )
