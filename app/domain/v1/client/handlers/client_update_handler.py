from kink import di

from app.common.errors.errors import DatabaseError, ResourceNotFoundError
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
        try:
            scopes = await self._validate_scopes(request.data.scopes)
            client_id = request.req.path_params.get("client_id")

            # Check if client exists first
            existing_client = await self.db.client.find_unique(
                where={"client_id": client_id}
            )

            if not existing_client:
                raise ResourceNotFoundError(
                    resource_type="client",
                    resource_id=client_id,
                    trace_id=request.trace_id,
                    request_id=request.request_id,
                )

            client = await self.db.client.update(
                where={"client_id": client_id},
                data={
                    "is_active": request.data.is_active,
                    "scopes": {"set": [{"id": scope.id} for scope in scopes]},
                },
                include={"scopes": True},
            )

            if not client:
                raise DatabaseError(
                    message="failed to update client",
                    operation="update",
                    table_name="clients",
                    trace_id=request.trace_id,
                    request_id=request.request_id,
                )

            data = client.model_dump()
            data["scopes"] = [scope.name for scope in scopes]

            return ClientUpdateResponse(
                trace_id=request.trace_id,
                request_id=request.request_id,
                data=ClientUpdateOutput(**data),
            )

        except (ResourceNotFoundError, DatabaseError):
            raise

        except Exception as e:
            raise DatabaseError(
                message="unexpected error during client update",
                operation="update",
                table_name="clients",
                trace_id=request.trace_id,
                request_id=request.request_id,
                cause=e,
            ) from e
