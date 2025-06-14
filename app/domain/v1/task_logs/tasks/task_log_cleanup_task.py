import uuid
from typing import Any

from kink import di
from pydiator_core.mediatr import pydiator

from app.common.errors.errors import ErrorCode, TaskError
from app.common.utils import PydiatorBuilder
from app.core.config import Configuration
from app.domain.v1.task_logs.requests import TaskLogCleanupRequest
from app.infrastructure.taskiq.schemas import TaskPriority
from app.infrastructure.taskiq.task_manager import TaskManager

config = di[Configuration].task_logging
tm = di[TaskManager]

_trace_id = str(uuid.uuid4())
_request_id = str(uuid.uuid4())


@tm.broker.task(
    "task_log:cleanup",
    priority=TaskPriority.LOW.to_taskiq_priority(),
    retry_on_error=True,
    kwargs={},
    max_retries=2,
    schedule=[{"cron": f"0 */{getattr(config, 'cleanup_interval_hours', 24)} * * *"}],
    trace_id=_trace_id,
    request_id=_request_id,
)
async def task_log_cleanup_task() -> dict[str, Any]:
    try:
        return (
            await pydiator.send(
                PydiatorBuilder.build(
                    TaskLogCleanupRequest,
                    None,
                    trace_id=_trace_id,
                    request_id=_request_id,
                )
            )
        ).data.model_dump()

    except Exception as e:
        raise TaskError(
            error_code=ErrorCode.TASK_EXECUTION_ERROR,
            message="task log cleanup task failed",
            task_name="task_log:cleanup",
            trace_id=_trace_id,
            request_id=_request_id,
        ) from e
