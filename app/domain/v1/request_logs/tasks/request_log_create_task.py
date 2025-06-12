from typing import Any

from kink import di
from pydiator_core.mediatr import pydiator

from app.common.utils import PydiatorBuilder
from app.domain.v1.request_logs.requests import RequestLogCreateRequest
from app.domain.v1.request_logs.schemas import RequestLogCreateInput
from app.infrastructure.database import Database
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
async def request_log_create_task(
    data: dict[str, Any], **kwargs: Any
) -> dict[str, Any]:
    try:
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

    except Exception:
        raise
