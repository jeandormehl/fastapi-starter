from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.clients import router as client_router
from app.api.v1.health import router as health_router
from app.api.v1.scopes import router as scope_router

router = APIRouter()

# additional routers
router.include_router(health_router)
router.include_router(auth_router)
router.include_router(client_router)
router.include_router(scope_router)
