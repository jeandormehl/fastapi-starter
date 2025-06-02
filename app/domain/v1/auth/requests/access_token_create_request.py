from app.domain.common import BaseRequest
from app.domain.v1.auth.schemas import AccessTokenCreateInput


class AccessTokenCreateRequest(BaseRequest):
    data: AccessTokenCreateInput
