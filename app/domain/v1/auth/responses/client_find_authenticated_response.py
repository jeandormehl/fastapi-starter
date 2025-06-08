from app.common.base_response import BaseResponse
from app.domain.v1.auth.schemas import ClientOut


class ClientFindAuthenticatedResponse(BaseResponse):
    data: ClientOut
