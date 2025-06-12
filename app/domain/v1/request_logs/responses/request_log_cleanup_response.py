from app.common.base_response import BaseResponse
from app.domain.v1.request_logs.schemas import RequestLogCleanupOutput


class RequestLogCleanupResponse(BaseResponse):
    data: RequestLogCleanupOutput
