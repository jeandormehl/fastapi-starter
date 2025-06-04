from datetime import datetime
from enum import Enum
from typing import Protocol, runtime_checkable

from pydantic.dataclasses import dataclass


class BrokerType(str, Enum):
    """Supported broker types."""

    REDIS = "redis"
    RABBITMQ = "rabbitmq"
    MEMORY = "memory"


class TaskPriority(str, Enum):
    """Task priority levels."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class TaskStatus(str, Enum):
    """Task execution status."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


@dataclass
class TaskExecutionMetrics:
    """Task execution metrics."""

    task_id: str
    task_name: str
    start_time: datetime
    end_time: datetime | None = None
    duration_seconds: float | None = None
    status: TaskStatus = TaskStatus.PENDING
    retry_count: int = 0
    memory_usage_mb: float | None = None
    cpu_usage_percent: float | None = None


@dataclass
class BrokerHealthStatus:
    """Broker health status information."""

    is_healthy: bool
    broker_type: BrokerType
    connection_pool_size: int
    active_connections: int
    last_health_check: datetime
    error_message: str | None = None
    response_time_ms: float | None = None


@runtime_checkable
class TaskiqMetricsCollector(Protocol):
    """Protocol for metrics collection."""

    async def record_task_started(self, metrics: TaskExecutionMetrics) -> None:
        """Record task start metrics."""

    async def record_task_completed(self, metrics: TaskExecutionMetrics) -> None:
        """Record task completion metrics."""

    async def record_task_failed(
        self, metrics: TaskExecutionMetrics, error: Exception
    ) -> None:
        """Record task failure metrics."""
