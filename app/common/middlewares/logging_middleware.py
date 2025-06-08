import time
from datetime import datetime
from typing import Any

from fastapi import Request
from kink import di
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp

from app.common.logging import get_logger
from app.common.utils import ClientIPExtractor, DataSanitizer, TraceContextExtractor
from app.core.config import Configuration
from app.infrastructure.taskiq.schemas import TaskPriority
from app.infrastructure.taskiq.task_manager import TaskManager


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Unified logging middleware that handles both basic request logging
    and comprehensive database logging based on configuration.
    Eliminates overlap between multiple logging middlewares.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

        self.config = di[Configuration]
        self.logger = get_logger(__name__)
        self.task_manager = di[TaskManager]

        # Performance tracking
        self._request_count = 0
        self._error_count = 0
        self._skip_count = 0

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Process request with unified logging capabilities."""

        # Quick skip check
        if not self._should_process_request(request):
            self._skip_count += 1
            return await call_next(request)

        start_time = time.time()
        start_datetime = datetime.now(di["timezone"])

        # Store start time in request state
        request.state.start_time = start_time

        try:
            # Create request context for logging
            request_context = self._create_request_context(request, start_datetime)

            # Basic request logging
            self.logger.bind(**request_context).info("request started")

            # Process request
            response = await call_next(request)

            # Calculate duration and create response context
            duration = time.time() - start_time
            end_datetime = datetime.now(di["timezone"])

            response_context = self._create_response_context(
                request, response, end_datetime, duration
            )

            # Basic response logging
            self.logger.bind(**response_context).info("request completed successfully")

            # Database logging if enabled
            if self.config.request_logging_enabled:
                await self._submit_database_logging(
                    {**request_context, **response_context}
                )

            # Add performance header
            response.headers["X-Response-Time"] = f"{duration:.3f}s"

            self._request_count += 1
            return response

        except Exception as exc:
            self._error_count += 1
            self.logger.bind(
                trace_id=TraceContextExtractor.get_trace_id(request),
                request_id=TraceContextExtractor.get_request_id(request),
                error=str(exc),
            ).error("critical error in logging middleware")

            # Continue request processing even if logging fails
            return await call_next(request)

    def _create_request_context(
        self, request: Request, start_datetime: datetime
    ) -> dict[str, Any]:
        """Create comprehensive request context for logging."""

        trace_id = TraceContextExtractor.get_trace_id(request)
        request_id = TraceContextExtractor.get_request_id(request)

        context = {
            "trace_id": trace_id,
            "request_id": request_id,
            "method": request.method,
            "url": str(request.url),
            "path": request.url.path,
            "query_params": str(request.query_params) if request.query_params else None,
            "content_type": request.headers.get("content-type"),
            "content_length": self._safe_int(request.headers.get("content-length")),
            "client_ip": ClientIPExtractor.extract_client_ip(request),
            "user_agent": request.headers.get("user-agent"),
            "start_time": start_datetime,
            "event": "request_started",
        }

        # Add headers if configured
        if self.config.request_logging_log_headers:
            context["headers"] = DataSanitizer.sanitize_headers(dict(request.headers))

        # Add authentication info
        context.update(self._extract_auth_info(request))

        return context

    def _create_response_context(
        self,
        request: Request,
        response: Response,
        end_datetime: datetime,
        duration: float,
    ) -> dict[str, Any]:
        """Create comprehensive response context for logging."""

        context = {
            "status_code": response.status_code,
            "response_size": self._safe_int(response.headers.get("content-length")),
            "end_time": end_datetime,
            "duration_ms": round(duration * 1000, 2),
            "response_type": response.__class__.__name__,
            "event": "request_completed",
        }

        # Add response headers if configured
        if self.config.request_logging_log_headers:
            context["response_headers"] = DataSanitizer.sanitize_headers(
                dict(response.headers)
            )

        # Add error information for non-2xx responses
        if response.status_code >= 400:
            context.update(self._extract_error_info(request, response))

        return context

    def _extract_auth_info(self, request: Request) -> dict[str, Any]:
        """Extract authentication information with defensive programming."""

        auth_info = {
            "authenticated": False,
            "client_id": None,
            "scopes": [],
            "auth_method": None,
            "has_bearer_token": False,
        }

        # Check request state for authentication
        if hasattr(request, "state") and hasattr(request.state, "client"):
            client = getattr(request.state, "client", None)
            if client:
                auth_info.update(
                    {
                        "authenticated": True,
                        "client_id": getattr(client, "client_id", None),
                    }
                )

                scopes = getattr(client, "scopes", [])
                if scopes:
                    auth_info["scopes"] = [scope.name for scope in client.scopes]

        # Check for JWT token presence
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            auth_info["has_bearer_token"] = True

        return auth_info

    def _extract_error_info(
        self, _request: Request, response: Response
    ) -> dict[str, Any]:
        """Extract error information for failed requests."""

        return {
            "error_occurred": True,
            "error_category": self._categorize_error(response.status_code),
            "error_type": f"http_{response.status_code}",
            "error_message": f"http {response.status_code} error occurred",
        }

    def _categorize_error(self, status_code: int) -> str:
        """Categorize errors by HTTP status code."""

        error_categories = {
            400: "bad_request",
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            422: "validation_error",
            500: "internal_server_error",
            502: "bad_gateway",
            503: "service_unavailable",
        }

        if status_code in error_categories:
            return error_categories[status_code]

        if 400 <= status_code < 500:
            return "client_error"

        if 500 <= status_code < 600:
            return "server_error"

        return "unknown_error"

    async def _submit_database_logging(self, log_data: dict[str, Any]) -> None:
        """Submit comprehensive logging task for database storage."""

        try:
            # Add metadata
            log_data.update(
                {
                    "logged_at": datetime.now(di["timezone"]),
                    "request_count": self._request_count,
                }
            )

            # Submit with proper error handling
            await self.task_manager.submit_task(
                "request_log:create",
                log_data,
                priority=TaskPriority.LOW,
                max_retries=3,
                retry_delay=1.0,
            )

        except Exception as e:
            self.logger.bind(
                trace_id=log_data.get("trace_id"),
                request_id=log_data.get("request_id"),
                error=str(e),
            ).error("failed to submit request logging task")

    def _should_process_request(self, request: Request) -> bool:
        """Determine if request should be processed for logging."""

        path = request.url.path

        # Skip health check, docs and metrics endpoints
        skip_endpoints = {
            "/health",
            "/metrics",
            "/v1",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/static",
        }

        if path in skip_endpoints:
            return False

        # Check excluded paths
        for excluded_path in getattr(self.config, "request_logging_excluded_paths", []):
            if path.startswith(excluded_path):
                return False

        # Check excluded methods
        excluded_methods = getattr(self.config, "request_logging_excluded_methods", [])

        return request.method.upper() not in excluded_methods

    def _safe_int(self, value: str | None) -> int | None:
        """Safely convert string to int."""

        if value is None:
            return None

        try:
            return int(value)

        except (ValueError, TypeError):
            return None

    async def get_middleware_stats(self) -> dict[str, Any]:
        """Get middleware performance statistics."""

        return {
            "total_requests_processed": self._request_count,
            "total_errors": self._error_count,
            "total_skipped": self._skip_count,
            "error_rate": self._error_count / max(self._request_count, 1),
            "skip_rate": self._skip_count
            / max(self._request_count + self._skip_count, 1),
        }
