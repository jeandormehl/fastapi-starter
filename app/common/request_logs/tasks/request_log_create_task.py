from typing import Any

from kink import di, inject

from app.core.logging import get_logger
from app.infrastructure.database import Database
from app.infrastructure.taskiq.task_manager import TaskManager

tm = di[TaskManager]


@inject
@tm.broker.task("request_log:create", max_retries=3)
async def request_log_create_task(
    db: Database, data: dict[str, Any]
) -> dict[str, Any] | Exception:
    logger = get_logger(__name__)

    try:
        # Insert into database
        request_log = await db.requestlog.create(data=data)

        logger.bind(
            trace_id=data.get("trace_id", "unknown"),
            request_id=data.get("request_id", "unknown"),
        ).debug("request log successfully saved to database")

        return {"success": True, request_log: {"id": request_log.id}}
    except Exception as e:
        logger.bind(
            trace_id=data.get("trace_id", "unknown"),
            request_id=data.get("request_id", "unknown"),
            error=str(e),
        ).error("failed to save request log to database")

        # Re-raise to trigger retry mechanism
        raise
