from datetime import datetime

from fastapi import APIRouter
from fastapi.requests import Request
from kink import di
from pydiator_core.mediatr import pydiator

from app.common.utils import PydiatorBuilder
from app.domain.v1.health.requests import HealthCheckRequest
from app.domain.v1.health.schemas import HealthCheckOutput, HealthLivenessOutput

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/")
async def health_check(request: Request) -> HealthCheckOutput:
    return (
        await pydiator.send(PydiatorBuilder.build(HealthCheckRequest, request))
    ).data


@router.get("/liveness")
async def liveness_check() -> HealthLivenessOutput:
    """
    Simple liveness probe for container orchestration
    Returns 200 if the application is running
    """

    return HealthLivenessOutput(
        status="alive",
        timestamp=datetime.now(di["timezone"]).isoformat(),
    )
