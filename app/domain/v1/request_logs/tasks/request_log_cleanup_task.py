import uuid
from typing import Any

from kink import di
from pydiator_core.mediatr import pydiator

from app.common.utils import PydiatorBuilder
from app.core.config import Configuration
from app.domain.v1.request_logs.requests import RequestLogCleanupRequest
from app.infrastructure.taskiq.schemas import TaskPriority
from app.infrastructure.taskiq.task_manager import TaskManager

config = di[Configuration]
tm = di[TaskManager]

_trace_id = str(uuid.uuid4())
_request_id = str(uuid.uuid4())


@tm.broker.task(
    "request_log:cleanup",
    priority=TaskPriority.LOW.to_taskiq_priority(),
    retry_on_error=True,
    kwargs={},
    max_retries=2,
    schedule=[
        {
            "cron": f"0 */{
                getattr(config, 'request_logging_cleanup_interval_hours', 24)
            } * * *"
        }
    ],
    trace_id=_trace_id,
    request_id=_request_id,
)
async def request_log_cleanup_task() -> dict[str, Any]:
    try:
        return (
            await pydiator.send(
                PydiatorBuilder.build(
                    RequestLogCleanupRequest,
                    None,
                    trace_id=_trace_id,
                    request_id=_request_id,
                )
            )
        ).data.model_dump()

    except Exception:
        raise
