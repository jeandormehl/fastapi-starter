from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from pydiator_core.interfaces import BaseHandler as PydiatorBaseHandler

from app.common.base_request import BaseRequest
from app.common.base_response import BaseResponse
from app.common.logging import get_logger

TRequest = TypeVar("TRequest", bound=BaseRequest)
TResponse = TypeVar("TResponse", bound=BaseResponse)


class BaseHandler(PydiatorBaseHandler, Generic[TRequest, TResponse], ABC):
    """
    Simplified base handler that focuses on business logic only.
    All error handling and logging is managed by middleware.
    """

    def __init__(self) -> None:
        super().__init__()

        self.logger = get_logger(self.__class__.__name__)

    @abstractmethod
    async def _handle_internal(self, request: TRequest) -> TResponse:
        """Handle the business logic for this request."""

    async def handle(self, request: TRequest) -> TResponse:
        """
        Handle the request - simplified to focus on business logic only.
        Error handling and logging are handled by middleware.
        """

        # Simple execution - middleware handles all cross-cutting concerns
        return await self._handle_internal(request)

    def log_business_event(
        self, event_name: str, event_data: dict | None = None, level: str = "info"
    ) -> None:
        """Log business events for analytics and monitoring."""

        event_context = {
            "event_name": event_name,
            "event_type": "business_event",
            "handler_class": self.__class__.__name__,
        }

        if event_data:
            event_context["event_data"] = event_data

        log_method = getattr(self.logger.bind(**event_context), level)
        log_method(f"business event: {event_name}")

    def log_performance_metric(
        self,
        metric_name: str,
        value: float,
        unit: str = "ms",
        additional_context: dict | None = None,
    ) -> None:
        """Log performance metrics for monitoring."""

        metric_context = {
            "metric_name": metric_name,
            "metric_value": value,
            "metric_unit": unit,
            "metric_type": "performance",
            "handler_class": self.__class__.__name__,
        }

        if additional_context:
            metric_context.update(additional_context)

        self.logger.bind(**metric_context).info(f"performance metric: {metric_name}")
