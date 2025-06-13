from kink import di

from app.common.base_handler import BaseHandler
from app.common.errors.errors import DatabaseError
from app.common.logging import get_logger
from app.common.utils import PrismaDataTransformer
from app.domain.v1.idempotency.services.idempotency_service import IdempotencyService
from app.domain.v1.request_logs.requests import RequestLogCreateRequest
from app.domain.v1.request_logs.responses import RequestLogCreateResponse
from app.domain.v1.request_logs.schemas import RequestLogCreateOutput
from app.infrastructure.database import Database


class RequestLogCreateHandler(BaseHandler):
    def __init__(self) -> None:
        super().__init__()

        self.db = di[Database]
        self.idempotency_service = di[IdempotencyService]
        self.logger = get_logger(__name__)

    async def _handle_internal(
        self, request: RequestLogCreateRequest
    ) -> RequestLogCreateResponse:
        try:
            await Database.connect_db()

            self.logger.info(f"processing request log: {request.data.trace_id}")

            raw_data = request.data.model_dump()

            # Add idempotency fields if available
            if (
                hasattr(request.data, "idempotency_key")
                and request.data.idempotency_key
            ):
                raw_data["idempotency_key"] = request.data.idempotency_key
                raw_data["is_idempotent_retry"] = getattr(
                    request.data, "is_idempotent_retry", False
                )

                # Generate request hash if we have request details
                if all(
                    hasattr(request.data, field)
                    for field in ["request_method", "path", "body"]
                ):
                    headers = raw_data.get("headers", {})
                    body = str(raw_data.get("body", "")).encode()
                    raw_data["request_hash"] = (
                        self.idempotency_service.generate_request_hash(
                            method=raw_data["request_method"],
                            path=raw_data["path"],
                            body=body,
                            headers=headers,
                        )
                    )

            prisma_data = PrismaDataTransformer.prepare_data(raw_data, "RequestLog")
            request_log = await self.db.requestlog.create(data=prisma_data)

            return RequestLogCreateResponse(
                trace_id=request.data.trace_id,
                request_id=request.data.request_id,
                success=True,
                data=RequestLogCreateOutput(
                    success=True,
                    id=request_log.id,
                ),
            )

        except Exception as e:
            self.logger.bind(
                trace_id=request.data.trace_id,
                request_id=request.data.request_id,
                error=str(e),
                error_type=type(e).__name__,
            ).error(f"failed to create request log: {e!s}")

            raise DatabaseError(
                message="failed to create request log",
                operation="create",
                table_name="requestlog",
                trace_id=request.data.trace_id,
                request_id=request.data.request_id,
                cause=e,
            ) from e
