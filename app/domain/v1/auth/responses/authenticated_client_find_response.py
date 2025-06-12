from app.common.base_response import BaseResponse
from app.domain.v1.auth.schemas import AuthenticatedClientOutput


class AuthenticatedClientFindResponse(BaseResponse):
    data: AuthenticatedClientOutput
