import contextlib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import NoReturn

from fastapi import FastAPI
from kink import di, inject
from prisma import Prisma
from starlette.staticfiles import StaticFiles

from app.api.v1 import v1_router
from app.core.config import Configuration
from app.core.logging import setup_logging
from app.core.paths import STATIC_PATH
from app.infrastructure.observability import (
    PrismaInstrumentation,
    configure_observability,
)


# noinspection PyBroadException
@asynccontextmanager  # type: ignore[arg-type]
@inject
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, NoReturn]:
    """Application lifespan manager."""
    try:
        setup_logging()
        PrismaInstrumentation().instrument_client(di[Prisma])

        if not di[Prisma].is_connected():
            await di[Prisma].connect()

        yield

    except Exception as e:
        print(e)
        contextlib.suppress(Exception)

    finally:
        if di[Prisma].is_connected():
            await di[Prisma].disconnect()


@inject
def get_application(config: Configuration) -> FastAPI:
    """Get FastAPI application.

    Add new versions:
        app_v2 = _v2(config)
        ...
        main.mount("/api/v2", app_v2)
    """
    v1_app = _v1(config)

    main = FastAPI(lifespan=lifespan)
    main.mount('/api/v1', v1_app)

    return main


def _v1(config: Configuration) -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        debug=config.app_debug,
        description=config.app_description,
        docs_url='/docs' if config.app_environment != 'prod' else None,
        openapi_url='/docs/openapi.json' if config.app_environment != 'prod' else None,
        redoc_url=None,
        title=config.app_name,
        version=config.app_version,
    )

    configure_observability(app, config)

    # Add middleware
    # register_request_middlewares(config, app)  TODO: Implement

    # Mount static files
    Path(STATIC_PATH).mkdir(parents=True, exist_ok=True)
    app.mount('/static', StaticFiles(directory=STATIC_PATH), name='static')

    # Include routers
    app.include_router(v1_router)

    return app
