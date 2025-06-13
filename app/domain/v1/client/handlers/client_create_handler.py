import uuid

from bcrypt import gensalt, hashpw
from kink import di

from app.common.errors.errors import DatabaseError, ValidationError
from app.domain.v1.client.requests import ClientCreateRequest
from app.domain.v1.client.responses import ClientCreateResponse
from app.domain.v1.client.schemas import ClientCreateOutput
from app.infrastructure.database import Database

from .base_client_handler import BaseClientHandler


class ClientCreateHandler(BaseClientHandler[ClientCreateRequest, ClientCreateResponse]):
    def __init__(self) -> None:
        super().__init__()

        self.db = di[Database]

    async def _handle_internal(
        self, request: ClientCreateRequest
    ) -> ClientCreateResponse:
        try:
            scopes = await self._validate_scopes(request.data.scopes)

            client = await self.db.client.create(
                data={
                    "client_id": str(uuid.uuid4()),
                    "name": request.data.name,
                    "hashed_secret": hashpw(
                        request.data.client_secret.encode("utf-8"), gensalt()
                    ).decode("utf-8"),
                    "scopes": {"connect": [{"id": scope.id} for scope in scopes]},
                },
                include={"scopes": True},
            )

            if not client:
                raise DatabaseError(
                    message="failed to create client",
                    operation="create",
                    table_name="clients",
                    trace_id=request.trace_id,
                    request_id=request.request_id,
                )

            data = client.model_dump()
            data["scopes"] = [scope.name for scope in scopes]

            return ClientCreateResponse(
                trace_id=request.trace_id,
                request_id=request.request_id,
                data=ClientCreateOutput(**data),
            )

        except (ValidationError, DatabaseError):
            raise

        except Exception as e:
            raise DatabaseError(
                message="unexpected error during client creation",
                operation="create",
                table_name="clients",
                trace_id=request.trace_id,
                request_id=request.request_id,
                cause=e,
            ) from e
