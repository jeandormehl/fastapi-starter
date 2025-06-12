from fastapi import APIRouter
from fastapi.requests import Request
from pydiator_core.mediatr import pydiator

from app.common.utils import PydiatorBuilder
from app.domain.v1.scopes.requests import ScopeFindRequest
from app.domain.v1.scopes.schemas import ScopeOutput

router = APIRouter(prefix="/scopes", tags=["scopes"])


@router.get("")
async def get_available_service_scopes(request: Request) -> list[ScopeOutput]:
    """Get available api scopes"""

    try:
        return (
            await pydiator.send(PydiatorBuilder.build(ScopeFindRequest, request))
        ).data

    except Exception:
        raise
