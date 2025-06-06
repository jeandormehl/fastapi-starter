from app.common import BaseHandler
from app.domain.v1.auth.requests import ClientFindAuthenticatedRequest
from app.domain.v1.auth.responses import (
    ClientFindAuthenticatedResponse,
)
from app.domain.v1.auth.schemas import ClientOut


class ClientFindAuthenticatedHandler(
    BaseHandler[ClientFindAuthenticatedRequest, ClientFindAuthenticatedResponse]
):
    async def _handle_internal(
        self, request: ClientFindAuthenticatedRequest
    ) -> ClientFindAuthenticatedResponse:
        data = request.client.model_dump()
        data["scopes"] = [scope.name for scope in request.client.scopes]

        return ClientFindAuthenticatedResponse(
            trace_id=request.trace_id,
            request_id=request.request_id,
            data=ClientOut(**data),
        )
