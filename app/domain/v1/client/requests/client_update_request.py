from app.common.base_request import BaseRequest
from app.domain.v1.client.schemas import ClientUpdateInput


class ClientUpdateRequest(BaseRequest):
    data: ClientUpdateInput
