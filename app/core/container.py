from zoneinfo import ZoneInfo

from fastapi import FastAPI
from httpx import Timeout
from kink import di
from prisma import Prisma
from prisma.types import HttpConfig

from app.core.application import get_application
from app.core.config import Configuration, get_config
from app.infrastructure.observability import MetricsAggregator


def wire_dependencies() -> None:
    _wire_core_dependencies()
    _wire_infrastructure_dependencies()
    _wire_services()
    _wire_mediatr()


# noinspection PyArgumentList
def _wire_core_dependencies() -> None:
    """Wire core application dependencies."""
    di[Configuration] = get_config()
    di[ZoneInfo] = ZoneInfo(di[Configuration].app_timezone)

    di[FastAPI] = get_application()  # type: ignore[call-arg]


def _wire_infrastructure_dependencies() -> None:
    di[Prisma] = Prisma(
        http=HttpConfig(
            timeout=Timeout(None, connect=di[Configuration].database.timeout)
        )
    )
    di[MetricsAggregator] = MetricsAggregator()


def _wire_services() -> None: ...


def _wire_mediatr() -> None: ...
