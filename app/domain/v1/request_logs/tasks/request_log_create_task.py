from typing import Any

from kink import di
from pydiator_core.mediatr import pydiator

from app.common.errors.errors import ErrorCode, TaskError
from app.common.utils import PydiatorBuilder
from app.domain.v1.request_logs.requests import RequestLogCreateRequest
from app.domain.v1.request_logs.schemas import RequestLogCreateInput
from app.infrastructure.database import Database
from app.infrastructure.taskiq.idempotent_task import idempotent_task
from app.infrastructure.taskiq.schemas import TaskPriority
from app.infrastructure.taskiq.task_manager import TaskManager

db = di[Database]
tm = di[TaskManager]


@tm.broker.task(
    "request_log:create",
    retry_on_error=True,
    max_retries=3,
    retry_delay=5.0,
    priority=TaskPriority.LOW.to_taskiq_priority(),
)
@idempotent_task()
async def request_log_create_task(
    data: dict[str, Any], idempotency_key: str | None = None, **kwargs: Any
) -> dict[str, Any]:
    """Enhanced task with idempotency support"""

    try:
        # Add idempotency key to data if provided
        if idempotency_key:
            data["idempotency_key"] = idempotency_key
            data["is_idempotent_retry"] = True

        return (
            await pydiator.send(
                PydiatorBuilder.build(
                    RequestLogCreateRequest,
                    None,
                    data=RequestLogCreateInput(**data),
                    trace_id=kwargs.get("trace_id"),
                    request_id=kwargs.get("request_id"),
                )
            )
        ).data.model_dump()

    except Exception as e:
        raise TaskError(
            error_code=ErrorCode.TASK_EXECUTION_ERROR,
            message="request log creation task failed",
            task_name="request_log:create",
            trace_id=kwargs.get("trace_id"),
            request_id=kwargs.get("request_id"),
        ) from e
