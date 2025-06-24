from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from kink import di

router = APIRouter(prefix='/health', tags=['health'])


@router.get('/liveness')
async def liveness_check() -> dict[str, Any]:
    """Simple liveness probe for container orchestration
    Returns 200 if the application is running.
    """
    return {
        'status': 'alive',
        'timestamp': datetime.now(di[ZoneInfo]).isoformat(),
    }
