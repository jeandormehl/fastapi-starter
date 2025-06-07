from typing import TypeVar
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from httpx import Timeout
from kink import di
from prisma.types import HttpConfig
from pydiator_core.mediatr import pydiator
from pydiator_core.mediatr_container import MediatrContainer
from taskiq import AsyncBroker

from app.core.application import get_application
from app.core.config import Configuration
from app.core.logging import initialize_logging
from app.domain.v1.auth.services import JWTService
from app.domain.v1.request_handler_map import RequestHandlerMap
from app.infrastructure.database import Database
from app.infrastructure.taskiq.broker.broker import get_broker
from app.infrastructure.taskiq.config import TaskiqConfiguration
from app.infrastructure.taskiq.task_manager import TaskManager

T = TypeVar("T")


# noinspection PyMethodMayBeStatic
class Container:
    """Dependency injection container."""

    def __init__(self) -> None:
        self._mediatr = MediatrContainer()
        self._is_wired = False

        self.wire()

    def wire(self) -> None:
        """Wire all dependencies."""
        if self._is_wired:
            return

        self._wire_core_dependencies()
        self._wire_infrastructure_dependencies()
        self._wire_services()
        self._wire_pydiator()

        self._is_wired = True

    # noinspection PyArgumentList
    def _wire_core_dependencies(self) -> None:
        """Wire core application dependencies."""

        # Configuration
        di[Configuration] = Configuration()
        di["timezone"] = ZoneInfo(di[Configuration].app_timezone)

        initialize_logging(di[Configuration])

        di[TaskiqConfiguration] = TaskiqConfiguration()

    def _wire_infrastructure_dependencies(self) -> None:
        """Wire infrastructure dependencies."""

        # prisma
        di[Database] = Database(http=HttpConfig(timeout=Timeout(180)))

        # fastapi
        di[FastAPI] = get_application(di[Configuration])

        # taskiq
        di[AsyncBroker] = get_broker(di[TaskiqConfiguration])
        di[TaskManager] = TaskManager(di[AsyncBroker])

    def _wire_services(self) -> None:
        di[JWTService] = JWTService(di[Configuration])

    def _wire_pydiator(self) -> None:
        """Configure pydiator mediator."""

        self._register_handlers()

        pydiator.ready(container=self._mediatr)

    def _register_handlers(self) -> None:
        """Register all handlers from configuration"""

        for config in RequestHandlerMap:
            request_type, handler_cls = config.value

            # Register handler in DI container as factory
            di.factories[handler_cls] = lambda _, handler=handler_cls: handler()
            self._mediatr.register_request(request_type, di[handler_cls])

    def get_dependency(self, dependency_type: type[T]) -> T:
        """Get a dependency from the container."""

        return di[dependency_type]


# Global container instance
container = Container()
