import inspect
import json
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar, get_args, get_origin

from kink import di
from pydiator_core.interfaces import BaseHandler as PydiatorBaseHandler

from app.common.base_request import BaseRequest
from app.common.base_response import BaseResponse
from app.common.logging import get_logger
from app.domain.v1.idempotency.services.idempotency_service import IdempotencyService

TRequest = TypeVar("TRequest", bound=BaseRequest)
TResponse = TypeVar("TResponse", bound=BaseResponse)


class BaseHandler(PydiatorBaseHandler, Generic[TRequest, TResponse], ABC):
    """Base handler with optional idempotency support"""

    def __init__(self) -> None:
        super().__init__()

        self.logger = get_logger(self.__class__.__name__)
        self.idempotency_service = di[IdempotencyService]

    @abstractmethod
    async def _handle_internal(self, request: TRequest) -> TResponse:
        """Handle the business logic for this request."""

    async def handle(self, request: TRequest) -> TResponse:
        """Handle request with optional idempotency support"""

        # Check if idempotency should be applied
        if not self._should_apply_idempotency(request):
            return await self._handle_internal(request)

        # Extract idempotency key from request
        idempotency_key = self._extract_idempotency_key(request)
        if not idempotency_key:
            return await self._handle_internal(request)

        # Generate request hash for content verification
        content_hash = await self._generate_request_hash(request)

        # Check for duplicate request
        idempotency_result = await self.idempotency_service.check_request_idempotency(
            idempotency_key=idempotency_key,
            method=request.req.method if request.req else "UNKNOWN",
            path=request.req.url.path if request.req else "",
            content_hash=content_hash,
            _client_id=getattr(request.client, "client_id", None)
            if request.client
            else None,
        )

        if idempotency_result.is_duplicate:
            # Return cached response
            self.logger.info(
                f"returning cached response for idempotency key: {idempotency_key}",
                extra={"idempotency_key": idempotency_key, "cache_hit": True},
            )

            # Convert cached response back to domain response
            return await self._build_cached_response(
                request, idempotency_result.cached_response
            )

        # Process new request
        response = await self._handle_internal(request)

        # Cache successful response for future idempotency checks
        if self._should_cache_response(response):
            await self._cache_response(request, response, idempotency_key, content_hash)

        return response

    def _should_apply_idempotency(self, request: TRequest) -> bool:
        """Determine if idempotency should be applied to this request"""

        if not request.req:
            return False

        return self.idempotency_service.should_apply_request_idempotency(
            request.req.method, request.req.url.path
        )

    def _extract_idempotency_key(self, request: TRequest) -> str | None:
        """Extract idempotency key from request headers"""

        if not request.req:
            return None

        return self.idempotency_service.extract_idempotency_key(
            dict(request.req.headers)
        )

    async def _generate_request_hash(self, request: TRequest) -> str:
        """Generate hash of request content for verification"""

        if not request.req:
            return ""

        # Get request body
        body = b""
        if hasattr(request.req, "_body"):
            # noinspection PyProtectedMember
            body = request.req._body

        elif hasattr(request, "data") and request.data:
            body = json.dumps(request.data.model_dump(), sort_keys=True).encode()

        return self.idempotency_service.generate_request_hash(
            method=request.req.method,
            path=request.req.url.path,
            body=body,
            headers=dict(request.req.headers),
        )

    async def _build_cached_response(
        self, request: TRequest, cached_data: dict
    ) -> TResponse:
        """Build response object from cached data"""

        # This creates a generic response - you may need to customize per handler
        response_class = self._get_response_class()

        return response_class(
            trace_id=request.trace_id,
            request_id=request.request_id,
            data=cached_data.get("body"),
            _from_cache=True,  # Flag to indicate cached response
        )

    def _should_cache_response(self, response: TResponse) -> bool:
        """Determine if response should be cached"""

        # Only cache successful responses
        return hasattr(response, "data") and response.data is not None

    async def _cache_response(
        self,
        request: TRequest,
        response: TResponse,
        idempotency_key: str,
        content_hash: str,
    ) -> None:
        """Cache response for future idempotency checks"""

        try:
            response_data = (
                response.data.model_dump()
                if hasattr(response.data, "model_dump")
                else response.data
            )

            await self.idempotency_service.cache_request_response(
                idempotency_key=idempotency_key,
                method=request.req.method if request.req else "UNKNOWN",
                path=request.req.url.path if request.req else "",
                content_hash=content_hash,
                response_status=200,  # Assume success if we're caching
                response_body=response_data,
                response_headers={},
                client_id=getattr(request.client, "client_id", None)
                if request.client
                else None,
            )
        except Exception as e:
            self.logger.error(f"failed to cache response: {e}")

    def _get_response_class(self) -> Any:
        """Extract the actual response class from Generic type parameters"""

        try:
            # Method 1: Check __orig_bases__ for direct inheritance
            for base in getattr(self.__class__, "__orig_bases__", []):
                if get_origin(base) and issubclass(get_origin(base), BaseHandler):
                    args = get_args(base)

                    if len(args) >= 2:
                        return args[1]  # TResponse type

            # Method 2: Check MRO for parameterized generics
            for cls in self.__class__.__mro__:
                if hasattr(cls, "__orig_bases__"):
                    for base in cls.__orig_bases__:
                        if get_origin(base) and issubclass(
                            get_origin(base), BaseHandler
                        ):
                            args = get_args(base)

                            if len(args) >= 2:
                                return args[1]

            # Method 3: Try to infer from method annotations
            handle_method = getattr(self.__class__, "_handle_internal", None)

            if handle_method:
                sig = inspect.signature(handle_method)
                return_annotation = sig.return_annotation

                if return_annotation and return_annotation != inspect.Signature.empty:
                    return return_annotation

        except Exception as e:
            self.logger.warning(f"failed to introspect response type: {e}")

        # Fallback to base class
        from app.common.base_response import BaseResponse

        return BaseResponse

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
