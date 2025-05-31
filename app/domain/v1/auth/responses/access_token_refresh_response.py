from app.domain.common import BaseResponse
from app.domain.v1.auth.schemas.access_token import AccessTokenRefreshOutput


class AccessTokenRefreshResponse(BaseResponse):
    data: AccessTokenRefreshOutput
