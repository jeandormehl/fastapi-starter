from datetime import datetime, timedelta
from typing import Any

from kink import di, inject

from app.core.config import Configuration
from app.core.logging import get_logger
from app.infrastructure.database import Database
from app.infrastructure.taskiq.schemas import TaskPriority
from app.infrastructure.taskiq.task_manager import TaskManager

tm = di[TaskManager]


@inject
@tm.broker.task(
    "request_log:cleanup",
    priority=TaskPriority.LOW,
    max_retries=1,
    schedule=[{"cron": "*/1 * * * *"}],
)
async def request_log_cleanup_task(
    config: Configuration, db: Database
) -> dict[str, Any] | Exception:
    """
    Clean up old request logs based on retention configuration.

    Args:
        db: Database dependency
        config: Configuration dependency
    """

    logger = get_logger(__name__)

    try:
        # Calculate cutoff date
        retention_days = config.request_logging_retention_days
        cutoff_date = datetime.now(di["timezone"]) - timedelta(days=retention_days)

        # Delete old logs
        result = await db.requestlog.delete_many(
            where={"created_at": {"lt": cutoff_date}}
        )

        deleted_count = getattr(result, "count", 0)

        logger.bind(
            cutoff_date=cutoff_date.isoformat(),
            deleted_count=deleted_count,
            retention_days=retention_days,
        ).info("completed request logs cleanup")

        return {"success": True, "deleted_count": deleted_count}

    except Exception as e:
        logger.bind(
            retention_days=config.request_logging_retention_days, error=str(e)
        ).error("failed to cleanup old request logs")

        # Re-raise to trigger retry mechanism
        raise
