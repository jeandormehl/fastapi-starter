from app.common.base_response import BaseResponse
from app.domain.v1.request_logs.schemas import RequestLogCreateOutput


class RequestLogCreateResponse(BaseResponse):
    data: RequestLogCreateOutput
