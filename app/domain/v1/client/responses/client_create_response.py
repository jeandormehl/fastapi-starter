from app.common.base_response import BaseResponse
from app.domain.v1.client.schemas import ClientCreateOutput


class ClientCreateResponse(BaseResponse):
    data: ClientCreateOutput
