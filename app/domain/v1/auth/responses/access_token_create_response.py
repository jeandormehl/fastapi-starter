from app.common import BaseResponse
from app.domain.v1.auth.schemas import AccessTokenCreateOutput


class AccessTokenCreateResponse(BaseResponse):
    data: AccessTokenCreateOutput
