import contextlib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import NoReturn

from fastapi import FastAPI
from kink import inject
from starlette.staticfiles import StaticFiles

from app.api import router_v1
from app.common.constants import STATIC_PATH
from app.common.errors import EXCEPTION_HANDLERS
from app.common.middlewares import register_request_middlewares
from app.core.config import Configuration
from app.infrastructure.database import disconnect_db, init_db
from app.infrastructure.taskiq.task_manager import TaskManager


# noinspection PyUnusedLocal
@asynccontextmanager
@inject
async def lifespan(
    _app: FastAPI, task_manager: TaskManager
) -> AsyncGenerator[None, NoReturn]:
    """Application lifespan manager."""

    # Startup
    await init_db()
    await task_manager.start()

    yield

    # noinspection PyBroadException
    # Shutdown
    try:
        await task_manager.stop()
        await disconnect_db()

    except Exception:
        contextlib.suppress(Exception)


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

    # Add middleware
    register_request_middlewares(config, app)

    # Add exception handlers (order matters - most specific first)
    for exc_type, handler in EXCEPTION_HANDLERS.items():
        app.add_exception_handler(exc_type, handler)

    # Mount static files
    Path(STATIC_PATH).mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=STATIC_PATH), name="static")

    # Include routers
    app.include_router(router_v1)

    return app
