from kink import di

from app.common.base_handler import BaseHandler
from app.domain.v1.scopes.requests import ScopeFindRequest
from app.domain.v1.scopes.responses import ScopeFindResponse
from app.domain.v1.scopes.schemas import ScopeOutput
from app.infrastructure.database import Database


class ScopeFindHandler(BaseHandler[ScopeFindRequest, ScopeFindResponse]):
    def __init__(self) -> None:
        super().__init__()

        self.db = di[Database]

    async def _handle_internal(self, request: ScopeFindRequest) -> ScopeFindResponse:
        scopes = [
            ScopeOutput(**{"name": scope.name, "description": scope.description})
            for scope in await self.db.scope.find_many()
        ]

        return ScopeFindResponse(
            trace_id=request.trace_id, request_id=request.request_id, data=scopes
        )
