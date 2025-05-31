from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware import cors, gzip, trustedhost
from kink import inject
from starlette.staticfiles import StaticFiles

from app.api import router_v1
from app.api.middlewares.request_middleware import RequestMiddleware
from app.core.config import Configuration
from app.core.constants import STATIC_PATH
from app.core.errors.exception_handlers import EXCEPTION_HANDLERS
from app.infrastructure.database import disconnect_db, init_db


# noinspection PyUnusedLocal
@asynccontextmanager
@inject
async def lifespan(
    app: FastAPI,  # noqa: ARG001
) -> AsyncGenerator[None, Any]:
    """Application lifespan manager."""

    # Startup
    await init_db()

    yield

    # Shutdown
    await disconnect_db()


def get_application(config: Configuration) -> FastAPI:
    """
    Get FastAPI application.

    Add new versions:
        app_v2 = _v2(config)
        ...
        main.mount("/v2", app_v2)
    """

    app_v1 = _v1(config)

    main = FastAPI(lifespan=lifespan)
    main.mount("/v1", app_v1)

    return main


# noinspection PyTypeChecker
def _v1(config: Configuration) -> FastAPI:
    """Create and configure FastAPI application."""

    app = FastAPI(
        debug=config.app_debug,
        description=config.app_description,
        docs_url="/" if config.app_environment != "prod" else None,
        redoc_url=None,
        swagger_ui_parameters={"defaultModelsExpandDepth": -1},
        title=config.app_name,
        version=config.app_version,
    )

    # Add exception handlers (order matters - most specific first)
    for exc_type, handler in EXCEPTION_HANDLERS.items():
        app.add_exception_handler(exc_type, handler)

    # Add middleware
    app.add_middleware(gzip.GZipMiddleware, minimum_size=1000)
    app.add_middleware(
        trustedhost.TrustedHostMiddleware, allowed_hosts=config.api_allowed_hosts
    )
    app.add_middleware(
        cors.CORSMiddleware,
        allow_origins=config.api_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(RequestMiddleware)

    # Mount static files
    Path(STATIC_PATH).mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=STATIC_PATH), name="static")

    # Include routers
    app.include_router(router_v1)

    return app
