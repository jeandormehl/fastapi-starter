from app.common.base_response import BaseResponse
from app.domain.v1.idempotency.schemas import IdempotencyCacheCleanupOutput


class IdempotencyCacheCleanupResponse(BaseResponse):
    data: IdempotencyCacheCleanupOutput
