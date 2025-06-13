from datetime import datetime, timedelta

from kink import di

from app.common.base_handler import BaseHandler
from app.common.errors.errors import DatabaseError
from app.common.logging import get_logger
from app.core.config import Configuration
from app.domain.v1.task_logs.requests import TaskLogCleanupRequest
from app.domain.v1.task_logs.responses import TaskLogCleanupResponse
from app.domain.v1.task_logs.schemas import TaskLogCleanupOutput
from app.infrastructure.database import Database


class TaskLogCleanupHandler(BaseHandler):
    def __init__(self) -> None:
        super().__init__()

        self.db = di[Database]
        self.config = di[Configuration]
        self.logger = get_logger(__name__)

    async def _handle_internal(
        self, request: TaskLogCleanupRequest
    ) -> TaskLogCleanupResponse:
        try:
            # noinspection DuplicatedCode
            await Database.connect_db()

            retention_days = self.config.task_logging_retention_days
            cutoff_date = datetime.now(di["timezone"]) - timedelta(days=retention_days)

            total_deleted = await self.db.tasklog.delete_many(
                where={"created_at": {"lt": cutoff_date}}
            )

            self.logger.bind(
                cutoff_date=cutoff_date.isoformat(),
                total_deleted=total_deleted,
                retention_days=retention_days,
            ).info("completed task logs cleanup")

            return TaskLogCleanupResponse(
                trace_id=request.trace_id,
                request_id=request.request_id,
                data=TaskLogCleanupOutput(
                    success=True,
                    total_deleted=total_deleted,
                    cutoff_date=cutoff_date.isoformat(),
                    retention_days=retention_days,
                ),
            )

        except Exception as e:
            self.logger.bind(
                trace_id=request.trace_id,
                request_id=request.request_id,
                retention_days=self.config.task_logging_retention_days,
                error=str(e),
                error_type=type(e).__name__,
            ).error("task logs cleanup failed")

            raise DatabaseError(
                message="failed to cleanup task logs",
                operation="delete_many",
                table_name="requestlog",
                trace_id=request.trace_id,
                request_id=request.request_id,
                cause=e,
            ) from e
