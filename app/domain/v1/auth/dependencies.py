from typing import TYPE_CHECKING, Annotated

from fastapi import Depends
from fastapi.requests import Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, SecurityScopes
from kink import di
from prisma.models import Client

from app.common.errors.errors import (
    ApplicationError,
    AuthenticationError,
    AuthorizationError,
    ErrorCode,
)
from app.domain.v1.auth.services import JWTService
from app.infrastructure.database import Database

if TYPE_CHECKING:
    from app.domain.v1.auth.schemas import JWTPayload

security = HTTPBearer()


class AuthenticationDependency:
    async def __call__(
        self,
        request: Request,
        security_scopes: SecurityScopes,
        credentials: HTTPAuthorizationCredentials = Depends(security),
    ) -> Client:
        self.db = di[Database]
        self.jwt_service = di[JWTService]

        # Verify the JWT token
        try:
            payload: JWTPayload = self.jwt_service.verify_token(credentials.credentials)
        except Exception:
            raise

        # Check if the token has required scopes
        if security_scopes.scopes:
            token_scopes = set(payload.scopes)
            required_scopes = set(security_scopes.scopes)

            if not required_scopes.issubset(token_scopes):
                msg = "insufficient permissions"
                raise AuthorizationError(msg, list(required_scopes))

        try:
            # noinspection PyTypeChecker
            client = await self.db.client.find_unique(
                where={"client_id": payload.client_id}, include={"scopes": True}
            )

            if not client:
                msg = "client not found"
                raise AuthenticationError(msg)

            # Verify client is still active
            if not client.is_active:
                msg = "client account is inactive"
                raise AuthenticationError(msg)

            request.state.client = client

            return client

        except AuthenticationError:
            raise

        except Exception as e:
            raise ApplicationError(
                ErrorCode.AUTHENTICATION_ERROR, "unknown authentication error", cause=e
            ) from e


# Convenience functions for common authentication scenarios
async def get_client(
    current_client: Client = Depends(AuthenticationDependency()),
) -> Client:
    """Get the current authenticated client without scope requirements."""
    return current_client


# Scope-specific dependencies
class RequireScopes:
    """Factory for creating scope-specific authentication dependencies."""

    def __init__(self, *scopes: str) -> None:
        self.required_scopes = set(scopes)

    async def __call__(
        self,
        current_client: Annotated[Client, Depends(AuthenticationDependency())],
        security_scopes: SecurityScopes,  # noqa: ARG002
    ) -> Client:
        missing_scopes = self.required_scopes - set(  # noqa: C403
            [scope.name for scope in current_client.scopes]
        )

        if missing_scopes:
            msg = "not enough permissions, missing scopes"
            raise AuthorizationError(msg, list(missing_scopes))

        return current_client


# Pre-defined scope dependencies
require_read_scope = RequireScopes("read")
require_write_scope = RequireScopes("write")
require_admin_scope = RequireScopes("admin")
