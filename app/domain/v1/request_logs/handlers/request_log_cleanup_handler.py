from datetime import datetime, timedelta

from kink import di

from app.common.base_handler import BaseHandler
from app.common.logging import get_logger
from app.core.config import Configuration
from app.domain.v1.request_logs.requests import RequestLogCleanupRequest
from app.domain.v1.request_logs.responses import RequestLogCleanupResponse
from app.domain.v1.request_logs.schemas import RequestLogCleanupOutput
from app.infrastructure.database import Database


class RequestLogCleanupHandler(BaseHandler):
    def __init__(self) -> None:
        super().__init__()

        self.db = di[Database]
        self.config = di[Configuration]
        self.logger = get_logger(__name__)

    async def _handle_internal(
        self, request: RequestLogCleanupRequest
    ) -> RequestLogCleanupResponse:
        try:
            await Database.connect_db()

            # Calculate cutoff date
            retention_days = self.config.request_logging_retention_days
            cutoff_date = datetime.now(di["timezone"]) - timedelta(days=retention_days)

            result = await self.db.requestlog.delete_many(
                where={"created_at": {"lt": cutoff_date}}
            )

            total_deleted = getattr(result, "count", 0)

            self.logger.bind(
                cutoff_date=cutoff_date.isoformat(),
                total_deleted=total_deleted,
                retention_days=retention_days,
            ).info("completed request logs cleanup")

            return RequestLogCleanupResponse(
                trace_id=request.trace_id,
                request_id=request.request_id,
                data=RequestLogCleanupOutput(
                    success=True,
                    total_deleted=total_deleted,
                    cutoff_date=cutoff_date.isoformat(),
                    retention_days=retention_days,
                ),
            )

        except Exception as e:
            self.logger.bind(
                trace_id=request.data.trace_id,
                request_id=request.data.request_id,
                retention_days=self.config.request_logging_retention_days,
                error=str(e),
                error_type=type(e).__name__,
            ).error("request logs cleanup failed")

            raise
