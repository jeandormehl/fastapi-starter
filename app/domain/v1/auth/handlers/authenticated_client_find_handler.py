from app.common.base_handler import BaseHandler
from app.domain.v1.auth.requests import AuthenticatedClientFindRequest
from app.domain.v1.auth.responses import (
    AuthenticatedClientFindResponse,
)
from app.domain.v1.auth.schemas import AuthenticatedClientOutput


class AuthenticatedClientFindHandler(
    BaseHandler[AuthenticatedClientFindRequest, AuthenticatedClientFindResponse]
):
    async def _handle_internal(
        self, request: AuthenticatedClientFindRequest
    ) -> AuthenticatedClientFindResponse:
        data = request.client.model_dump()
        data["scopes"] = [scope.name for scope in request.client.scopes]

        return AuthenticatedClientFindResponse(
            trace_id=request.trace_id,
            request_id=request.request_id,
            data=AuthenticatedClientOutput(**data),
        )
