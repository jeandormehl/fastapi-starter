import traceback
from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from pydiator_core.interfaces import BaseHandler as PydiatorBaseHandler

from app.core.errors.exceptions import AppException, ErrorCode
from app.core.logging import ContextualLogger, get_logger
from app.domain.common.base_request import BaseRequest
from app.domain.common.base_response import BaseResponse

TRequest = TypeVar("TRequest", bound=BaseRequest)
TResponse = TypeVar("TResponse", bound=BaseResponse)


class BaseHandler(PydiatorBaseHandler, Generic[TRequest, TResponse], ABC):
    """Base handler class with enhanced error handling and logging support."""

    logger: ContextualLogger

    def __init__(self):
        super().__init__()

        self.logger = get_logger(__name__)

    @abstractmethod
    async def _handle_internal(self, request: TRequest) -> TResponse:
        """Safely handle request with automatic error handling."""

    async def handle(self, request: TRequest) -> TResponse:
        """
        Handle the request and return a response with comprehensive error handling.
        """

        # Create contextual logger with trace information
        context_logger = self.logger.bind(
            handler=self.__class__.__name__,
            trace_id=request.trace_id,
            request_id=request.request_id,
            client_id=request.client.id if request.client else "unknown",
            handler_module=self.__class__.__module__,
        )

        # Log handler execution start
        context_logger.info(f"handler execution started: {self.__class__.__name__}")

        try:
            # Execute the handler logic
            result = await self._handle_internal(request)

            # Log successful execution
            context_logger.info(
                f"handler execution completed successfully: {self.__class__.__name__}"
            )

            return result

        except AppException as exc:
            # Ensure trace information is set on app exceptions
            if not exc.trace_id:
                exc.trace_id = request.trace_id
            if not exc.request_id:
                exc.request_id = request.request_id

            # Log application exception with context
            context_logger.bind(
                exception_type=type(exc).__name__,
                error_code=exc.error_code.value,
                status_code=exc.status_code,
            ).warning(f"handler raised application exception: {exc.message}")

            # Re-raise application exceptions as-is
            raise

        except Exception as exc:
            # Enhanced exception logging with full context
            tb = traceback.extract_tb(exc.__traceback__)

            exception_context = {
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
                "exception_module": getattr(exc.__class__, "__module__", "unknown"),
                "handler_class": self.__class__.__name__,
                "handler_module": self.__class__.__module__,
            }

            # Add traceback information
            if tb:
                last_frame = tb[-1]
                exception_context.update(
                    {
                        "error_function": last_frame.name,
                        "error_file": last_frame.filename,
                        "error_line": last_frame.lineno,
                        "error_code_context": last_frame.line,
                    }
                )

                # Add full traceback for debugging
                exception_context["full_traceback"] = traceback.format_exc()

            context_logger.bind(**exception_context).error(
                f"handler raised unexpected exception: {exc}", exc_info=exc
            )

            # Convert to application exception with enhanced details
            # noinspection PyUnboundLocalVariable
            raise AppException(
                error_code=ErrorCode.INTERNAL_SERVER_ERROR,
                message=f"handler '{self.__class__.__name__}' "
                f"encountered an unexpected error",
                details={
                    "handler_class": self.__class__.__name__,
                    "handler_module": self.__class__.__module__,
                    "original_exception": type(exc).__name__,
                    "original_message": str(exc),
                    "error_location": f"{last_frame.filename}:{last_frame.lineno}"
                    if tb
                    else "unknown",
                },
                trace_id=request.trace_id,
                request_id=request.request_id,
                cause=exc,
            ) from exc

    def log_performance_metric(
        self,
        metric_name: str,
        value: float,
        unit: str = "ms",
        additional_context: dict | None = None,
    ):
        """Log performance metrics for monitoring."""

        metric_context = {
            "metric_name": metric_name,
            "metric_value": value,
            "metric_unit": unit,
            "handler_class": self.__class__.__name__,
        }

        if additional_context:
            metric_context.update(additional_context)

        self.logger.bind(**metric_context).info("performance metric recorded")

    def log_business_event(self, event_name: str, event_data: dict | None = None):
        """Log business events for analytics and monitoring."""

        event_context = {
            "event_name": event_name,
            "handler_class": self.__class__.__name__,
        }

        if event_data:
            # noinspection PyTypeChecker
            event_context["event_data"] = event_data

        self.logger.bind(**event_context).info("business event occurred")
