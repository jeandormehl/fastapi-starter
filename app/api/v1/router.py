from fastapi import APIRouter

from .health import router as health_router
from .metrics import router as metrics_router
from .obs import router as demo_router

router = APIRouter()

# additional routers
router.include_router(health_router)
router.include_router(metrics_router)
router.include_router(demo_router)
