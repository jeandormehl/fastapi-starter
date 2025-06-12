from app.common.base_request import BaseRequest
from app.domain.v1.client.schemas import ClientCreateInput


class ClientCreateRequest(BaseRequest):
    data: ClientCreateInput
