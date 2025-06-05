from app.common import BaseResponse
from app.domain.v1.auth.schemas import ScopeOut


class ScopeFindResponse(BaseResponse):
    data: list[ScopeOut]
