from app.domain.common import BaseResponse
from app.domain.v1.auth.schemas import ClientOut


class ClientFindAuthenticatedResponse(BaseResponse):
    data: ClientOut
