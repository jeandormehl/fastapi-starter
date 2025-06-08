from bcrypt import gensalt, hashpw
from kink import di
from prisma.models import Scope

from app.common.base_handler import BaseHandler
from app.common.errors.errors import DatabaseError, ValidationError
from app.domain.v1.auth.requests import ClientCreateRequest
from app.domain.v1.auth.responses import ClientCreateResponse
from app.domain.v1.auth.schemas import ClientOut
from app.infrastructure.database import Database


class ClientCreateHandler(BaseHandler[ClientCreateRequest, ClientCreateResponse]):
    def __init__(self) -> None:
        super().__init__()

        self.db = di[Database]

    async def _handle_internal(
        self, request: ClientCreateRequest
    ) -> ClientCreateResponse:
        scopes = await self._validate_scopes(request.data.scopes)

        # noinspection PyTypeChecker
        client = await self.db.client.create(
            data={
                "client_id": request.data.client_id,
                "hashed_secret": hashpw(
                    request.data.client_secret.encode("utf-8"), gensalt()
                ).decode("utf-8"),
                "scopes": {"connect": [{"id": scope.id} for scope in scopes]},
            },
            include={"scopes": True},
        )

        if not client:
            msg = "could not create client"
            raise DatabaseError(msg, "create", "clients")

        data = client.model_dump()
        data["scopes"] = [scope.name for scope in scopes]

        return ClientCreateResponse(
            trace_id=request.trace_id,
            request_id=request.request_id,
            data=ClientOut(**data),
        )

    async def _validate_scopes(self, scopes: list[str] | None = None) -> list[Scope]:
        existing_scopes = []

        if scopes:
            # noinspection PyTypeChecker
            existing_scopes: list[Scope] = await self.db.scope.find_many(
                where={"name": {"in": scopes}}
            )

            existing_scope_names = {scope.name for scope in existing_scopes}
            requested_scope_names = set(scopes)
            missing_scopes = requested_scope_names - existing_scope_names

            if missing_scopes:
                msg = "unknown scopes"
                raise ValidationError(msg, details={"scopes": list(missing_scopes)})

        return existing_scopes
