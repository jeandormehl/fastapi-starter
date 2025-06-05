from app.common import BaseRequest
from app.domain.v1.auth.schemas import ClientCreateInput


class ClientCreateRequest(BaseRequest):
    data: ClientCreateInput
