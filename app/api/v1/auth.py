from fastapi import APIRouter, Depends
from fastapi.requests import Request
from prisma.models import Client
from pydiator_core.mediatr import pydiator

from app.core.utils import build_pydiator_request
from app.domain.v1.auth.dependencies import get_client, require_admin_scope
from app.domain.v1.auth.requests import (
    AccessTokenCreateRequest,
    AccessTokenRefreshRequest,
    ClientCreateRequest,
    ClientFindAuthenticatedRequest,
    ScopeFindRequest,
)
from app.domain.v1.auth.schemas import (
    AccessTokenCreateInput,
    AccessTokenCreateOutput,
    ScopeOut,
)
from app.domain.v1.auth.schemas.access_token import AccessTokenRefreshOutput
from app.domain.v1.auth.schemas.client import ClientCreateInput, ClientOut

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/token")
async def create_new_access_token(
    request: Request,
    credentials: AccessTokenCreateInput,
) -> AccessTokenCreateOutput:
    """Create new access token from client credentials"""

    return (
        await pydiator.send(
            await build_pydiator_request(
                AccessTokenCreateRequest, request, data=credentials
            )
        )
    ).data


@router.post("/refresh")
async def refresh_access_token(
    request: Request,
    current_client: Client = Depends(get_client),
) -> AccessTokenRefreshOutput:
    """Refresh client access tokens"""

    return (
        await pydiator.send(
            await build_pydiator_request(
                AccessTokenRefreshRequest, request, client=current_client
            )
        )
    ).data


@router.post("/client")
async def create_new_service_client(
    request: Request,
    client: ClientCreateInput,
    current_client: Client = Depends(require_admin_scope),
) -> ClientOut:
    """Create new service client"""

    return (
        await pydiator.send(
            await build_pydiator_request(
                ClientCreateRequest, request, data=client, client=current_client
            )
        )
    ).data


@router.get("/client")
async def get_authenticated_client(
    request: Request,
    current_client: Client = Depends(get_client),
) -> ClientOut:
    """Get authenticated service client information"""

    return (
        await pydiator.send(
            await build_pydiator_request(
                ClientFindAuthenticatedRequest, request, client=current_client
            )
        )
    ).data


@router.get("/scopes")
async def get_available_scopes(request: Request) -> list[ScopeOut]:
    """Get available api scopes"""

    return (
        await pydiator.send(await build_pydiator_request(ScopeFindRequest, request))
    ).data
