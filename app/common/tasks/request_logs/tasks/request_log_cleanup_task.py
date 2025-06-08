from typing import Any

from kink import di

from app.common.logging import get_logger
from app.core.config import Configuration
from app.infrastructure.database import Database
from app.infrastructure.taskiq.schemas import TaskPriority
from app.infrastructure.taskiq.task_manager import TaskManager

config = di[Configuration]
db = di[Database]
tm = di[TaskManager]


@tm.broker.task(
    "request_log:cleanup",
    priority=TaskPriority.LOW,
    max_retries=2,
    schedule=[
        {"cron": "* * * * *"}
    ],  # TODO: CHANGE THIS -> {"cron": f"* */{config.request_logging_cleanup_interval_hours} * * *"}  # noqa: E501
)
async def request_log_cleanup_task() -> dict[str, Any]:
    """
    Cleanup task with better performance and monitoring.
    """
    logger = get_logger(__name__)

    try:
        from datetime import datetime, timedelta

        # Calculate cutoff date
        retention_days = config.request_logging_retention_days
        cutoff_date = datetime.now(di["timezone"]) - timedelta(days=retention_days)

        # Batch delete for better performance
        batch_size = 1000
        total_deleted = 0

        while True:
            # Delete in batches to avoid long-running transactions
            result = await db.requestlog.delete_many(
                where={"created_at": {"lt": cutoff_date}}, limit=batch_size
            )

            deleted_count = getattr(result, "count", 0)
            total_deleted += deleted_count

            if deleted_count < batch_size:
                break

        # Log cleanup statistics
        logger.bind(
            cutoff_date=cutoff_date.isoformat(),
            total_deleted=total_deleted,
            retention_days=retention_days,
            batch_size=batch_size,
        ).info("completed request logs cleanup")

        return {
            "success": True,
            "total_deleted": total_deleted,
            "cutoff_date": cutoff_date.isoformat(),
            "retention_days": retention_days,
        }

    except Exception as e:
        logger.bind(
            retention_days=config.request_logging_retention_days,
            error=str(e),
            error_type=type(e).__name__,
        ).error("request logs cleanup failed")

        raise
