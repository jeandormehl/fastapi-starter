from fastapi import APIRouter, Depends
from fastapi.requests import Request
from prisma.models import Client
from pydiator_core.mediatr import pydiator

from app.common.utils import PydiatorBuilder
from app.domain.v1.auth.dependencies import require_admin_scope
from app.domain.v1.client.requests import ClientCreateRequest, ClientUpdateRequest
from app.domain.v1.client.schemas import (
    ClientCreateInput,
    ClientCreateOutput,
    ClientUpdateInput,
    ClientUpdateOutput,
)

router = APIRouter(prefix="/clients", tags=["clients"])


@router.post("")
async def create_new_service_client(
    request: Request,
    data: ClientCreateInput,
    current_client: Client = Depends(require_admin_scope),
) -> ClientCreateOutput:
    """Create new service client"""

    return (
        await pydiator.send(
            PydiatorBuilder.build(
                ClientCreateRequest, request, data=data, client=current_client
            )
        )
    ).data


# noinspection PyUnusedLocal
@router.patch("/{client_id}")
async def update_existing_service_client(
    request: Request,
    client_id: str,  # noqa: ARG001
    data: ClientUpdateInput,
    current_client: Client = Depends(require_admin_scope),
) -> ClientUpdateOutput:
    """Update existing service client"""

    return (
        await pydiator.send(
            PydiatorBuilder.build(
                ClientUpdateRequest, request, data=data, client=current_client
            )
        )
    ).data
