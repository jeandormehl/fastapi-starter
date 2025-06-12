from kink import di

from app.common.errors.errors import DatabaseError
from app.domain.v1.client.requests import ClientUpdateRequest
from app.domain.v1.client.responses import ClientUpdateResponse
from app.infrastructure.database import Database

from ..schemas import ClientUpdateOutput
from .base_client_handler import BaseClientHandler


class ClientUpdateHandler(BaseClientHandler[ClientUpdateRequest, ClientUpdateResponse]):
    def __init__(self) -> None:
        super().__init__()

        self.db = di[Database]

    async def _handle_internal(
        self, request: ClientUpdateRequest
    ) -> ClientUpdateResponse:
        scopes = await self._validate_scopes(request.data.scopes)
        client_id = request.req.path_params.get("client_id")

        client = await self.db.client.update(
            where={"client_id": client_id},
            data={
                "is_active": request.data.is_active,
                "scopes": {"connect": [{"id": scope.id} for scope in scopes]},
            },
        )

        if not client:
            msg = "could not update client"
            raise DatabaseError(msg, "update", "clients")

        data = client.model_dump()
        data["scopes"] = [scope.name for scope in scopes]

        return ClientUpdateResponse(
            trace_id=request.trace_id,
            request_id=request.request_id,
            data=ClientUpdateOutput(**data),
        )
