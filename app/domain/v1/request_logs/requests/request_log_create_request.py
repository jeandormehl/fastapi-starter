from app.common.base_request import BaseRequest
from app.domain.v1.request_logs.schemas import RequestLogCreateInput


class RequestLogCreateRequest(BaseRequest):
    data: RequestLogCreateInput
