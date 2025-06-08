from kink import di

from app.common.base_handler import BaseHandler
from app.domain.v1.auth.requests import ScopeFindRequest
from app.domain.v1.auth.responses import ScopeFindResponse
from app.domain.v1.auth.schemas import ScopeOut
from app.infrastructure.database import Database


class ScopeFindHandler(BaseHandler[ScopeFindRequest, ScopeFindResponse]):
    def __init__(self) -> None:
        super().__init__()

        self.db = di[Database]

    async def _handle_internal(self, request: ScopeFindRequest) -> ScopeFindResponse:
        db_scopes = await self.db.scope.find_many()
        scopes = [
            ScopeOut(**{"name": scope.name, "description": scope.description})
            for scope in db_scopes
        ]

        return ScopeFindResponse(
            trace_id=request.trace_id, request_id=request.request_id, data=scopes
        )
