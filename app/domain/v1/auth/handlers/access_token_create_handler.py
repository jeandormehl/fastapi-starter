from bcrypt import checkpw
from kink import di

from app.core.errors.exceptions import AuthenticationException
from app.domain.common import BaseHandler
from app.domain.v1.auth.requests import AccessTokenCreateRequest
from app.domain.v1.auth.responses import AccessTokenCreateResponse
from app.domain.v1.auth.schemas import AccessTokenCreateOutput
from app.infrastructure.database import Database
from app.services import JWTService


class AccessTokenCreateHandler(BaseHandler):
    def __init__(self):
        super().__init__()

        self.database = di[Database]
        self.jwt_service = di[JWTService]

    async def _handle_internal(
        self, request: AccessTokenCreateRequest
    ) -> AccessTokenCreateResponse:
        try:
            # Find the client by client_id
            # noinspection PyTypeChecker
            client = await self.database.client.find_unique(
                where={"client_id": request.data.client_id}, include={"scopes": True}
            )

            if not client:
                msg = "invalid client credentials"
                raise AuthenticationException(msg)

            # Verify the secret
            if not checkpw(
                request.data.client_secret.encode("utf-8"),
                client.hashed_secret.encode("utf-8"),
            ):
                msg = "invalid client credentials"
                raise AuthenticationException(msg)

            # Check if client is active
            if not client.is_active:
                msg = "client account is inactive"
                raise AuthenticationException(msg)

            # Extract scopes from the client
            scopes = [scope.name for scope in client.scopes] if client.scopes else []

            # Create JWT tokens
            access_token = self.jwt_service.create_access_token(
                _id=client.id, client_id=client.client_id, scopes=scopes
            )

            response_data = AccessTokenCreateOutput(
                access_token=access_token,
                token_type="bearer",
                expires_in=self.jwt_service.access_token_expire_minutes * 60,
                scopes=" ".join(scopes) if scopes else None,
            )

            return AccessTokenCreateResponse(data=response_data)

        except Exception:
            raise
