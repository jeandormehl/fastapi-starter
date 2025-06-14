import uuid
from typing import Any

from kink import di
from pydiator_core.mediatr import pydiator

from app.common.errors.errors import ErrorCode, TaskError
from app.common.utils import PydiatorBuilder
from app.core.config import Configuration
from app.domain.v1.idempotency.requests import IdempotencyCacheCleanupRequest
from app.infrastructure.taskiq.schemas import TaskPriority
from app.infrastructure.taskiq.task_manager import TaskManager

config = di[Configuration].idempotency
tm = di[TaskManager]

_trace_id = str(uuid.uuid4())
_request_id = str(uuid.uuid4())


@tm.broker.task(
    "idempotency:cleanup",
    priority=TaskPriority.LOW.to_taskiq_priority(),
    retry_on_error=True,
    kwargs={},
    max_retries=2,
    schedule=[{"cron": f"0 */{getattr(config, 'cleanup_interval_hours', 24)} * * *"}],
    trace_id=_trace_id,
    request_id=_request_id,
)
async def cleanup_expired_idempotency_entries() -> dict[str, Any]:
    try:
        return (
            await pydiator.send(
                PydiatorBuilder.build(
                    IdempotencyCacheCleanupRequest,
                    None,
                    trace_id=_trace_id,
                    request_id=_request_id,
                )
            )
        ).data.model_dump()

    except Exception as e:
        raise TaskError(
            error_code=ErrorCode.TASK_EXECUTION_ERROR,
            message="idempotency cache cleanup task failed",
            task_name="idempotency:cleanup",
            trace_id=_trace_id,
            request_id=_request_id,
        ) from e
