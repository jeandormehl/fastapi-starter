from app.common.base_response import BaseResponse
from app.domain.v1.scopes.schemas import ScopeOutput


class ScopeFindResponse(BaseResponse):
    data: list[ScopeOutput]
