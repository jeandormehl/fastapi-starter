from datetime import datetime

from kink import di

from app.common.base_handler import BaseHandler
from app.common.errors.errors import ErrorCode, TaskError
from app.domain.v1.idempotency.requests import IdempotencyCacheCleanupRequest
from app.domain.v1.idempotency.responses import IdempotencyCacheCleanupResponse
from app.domain.v1.idempotency.schemas import IdempotencyCacheCleanupOutput
from app.domain.v1.idempotency.services.idempotency_service import IdempotencyService


class IdempotencyCacheCleanupHandler(BaseHandler):
    def __init__(self) -> None:
        super().__init__()

        self.idempotency_service = di[IdempotencyService]

    async def _handle_internal(
        self, request: IdempotencyCacheCleanupRequest
    ) -> IdempotencyCacheCleanupResponse:
        try:
            if not self.idempotency_service.is_enabled:
                return IdempotencyCacheCleanupResponse(
                    trace_id=request.trace_id,
                    request_id=request.request_id,
                    success=True,
                    data=IdempotencyCacheCleanupOutput(
                        success=True,
                        total_deleted=0,
                        message="idempotency is disabled",
                        timestamp=datetime.now(di["timezone"]).isoformat(),
                    ),
                )

            total_deleted = await self.idempotency_service.cleanup_expired_entries()

            return IdempotencyCacheCleanupResponse(
                trace_id=request.trace_id,
                request_id=request.request_id,
                success=True,
                data=IdempotencyCacheCleanupOutput(
                    success=True,
                    total_deleted=total_deleted,
                    timestamp=datetime.now(di["timezone"]).isoformat(),
                ),
            )

        except Exception as e:
            raise TaskError(
                error_code=ErrorCode.TASK_EXECUTION_ERROR,
                message="idempotency cleanup task failed",
                task_name="idempotency:cleanup",
                trace_id=request.trace_id,
                request_id=request.request_id,
            ) from e
