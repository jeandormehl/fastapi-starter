from fastapi import APIRouter, Depends
from fastapi.requests import Request
from prisma.models import Client
from pydiator_core.mediatr import pydiator

from app.common.utils import PydiatorBuilder
from app.domain.v1.auth.dependencies import get_client
from app.domain.v1.auth.requests import (
    AccessTokenCreateRequest,
    AccessTokenRefreshRequest,
    AuthenticatedClientFindRequest,
)
from app.domain.v1.auth.schemas import (
    AccessTokenCreateInput,
    AccessTokenCreateOutput,
    AccessTokenRefreshOutput,
    AuthenticatedClientOutput,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.get("")
async def get_authenticated_client(
    request: Request,
    current_client: Client = Depends(get_client),
) -> AuthenticatedClientOutput:
    """Get authenticated service client information"""

    try:
        return (
            await pydiator.send(
                PydiatorBuilder.build(
                    AuthenticatedClientFindRequest, request, client=current_client
                )
            )
        ).data

    except Exception:
        raise


@router.post("/token")
async def create_new_access_token(
    request: Request,
    credentials: AccessTokenCreateInput,
) -> AccessTokenCreateOutput:
    """Create new access token from client credentials"""

    try:
        return (
            await pydiator.send(
                PydiatorBuilder.build(
                    AccessTokenCreateRequest, request, data=credentials
                )
            )
        ).data

    except Exception:
        raise


@router.post("/refresh")
async def refresh_access_token(
    request: Request,
    current_client: Client = Depends(get_client),
) -> AccessTokenRefreshOutput:
    """Refresh client access tokens"""

    try:
        return (
            await pydiator.send(
                PydiatorBuilder.build(
                    AccessTokenRefreshRequest, request, client=current_client
                )
            )
        ).data

    except Exception:
        raise
