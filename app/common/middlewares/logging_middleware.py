import time
from datetime import datetime
from typing import Any

from fastapi import Request
from kink import di
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp

from app.common.logging import get_logger
from app.common.utils import (
    BodyProcessor,
    ClientIPExtractor,
    DataSanitizer,
    TraceContextExtractor,
)
from app.core.config import Configuration
from app.infrastructure.taskiq.task_manager import TaskManager


# noinspection PyBroadException
class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Logging middleware that handles comprehensive request/response logging
    with database persistence and performance tracking.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

        self.config = di[Configuration]
        self.logger = get_logger(__name__)
        self.task_manager = di[TaskManager]

        # Performance tracking
        self._request_count = 0
        self._skip_count = 0

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Process request with unified logging capabilities."""

        # Quick skip check for non-business endpoints
        if not self._should_process_request(request):
            self._skip_count += 1
            return await call_next(request)

        start_time = time.time()
        start_datetime = datetime.now(di["timezone"])

        # Store start time in request state
        request.state.start_time = start_time

        try:
            # Create request context for logging
            request_context = await self._create_request_context(
                request, start_datetime
            )

            # Log request start
            self.logger.bind(**request_context).info("request started")

            # Process request
            response = await call_next(request)

            # Capture response body using the extracted function
            response_body, response = await self._get_safe_response_body(response)

            # Calculate duration and create response context
            duration = time.time() - start_time
            end_datetime = datetime.now(di["timezone"])

            response_context = self._create_response_context(
                request, response, end_datetime, duration, response_body
            )

            # Log successful completion
            complete_context = {**request_context, **response_context}
            santized_context = DataSanitizer.sanitize_data(complete_context)
            self.logger.bind(**santized_context).info("request completed successfully")

            # Database logging if enabled
            if self.config.request_logging_enabled:
                await self._submit_database_logging(complete_context)

            # Add performance headers
            response.headers["X-Response-Time"] = f"{duration:.3f}s"
            response.headers["X-Request-Count"] = str(self._request_count)

            self._request_count += 1
            return response

        except Exception as exc:
            # Log middleware failure but don't interfere with error handling
            self.logger.bind(
                trace_id=TraceContextExtractor.get_trace_id(request),
                request_id=TraceContextExtractor.get_request_id(request),
                error=str(exc),
                middleware="logging",
            ).error("logging middleware encountered an error")

            # Re-raise to let error middleware handle it
            raise

    async def _safe_get_request_body(self, request: Request) -> dict[str, Any] | None:
        """Safely get request body without consuming the stream."""

        try:
            # Check if request has a body
            if request.headers.get("content-length") == "0":
                return None

            content_type = request.headers.get("content-type", "")
            if "application/json" in content_type:
                return await request.json()

            # For non-JSON content, return None or handle appropriately
            return None

        except Exception:
            return None

    # noinspection PyUnresolvedReferences
    async def _get_safe_response_body(self, response: Response) -> tuple[Any, Response]:
        """
        Safely capture response body without breaking FastAPI's streaming mechanism.

        Returns:
            tuple: (response_body_data, new_response_object)
        """

        try:
            # Read response body using streaming approach
            chunks = []
            async for chunk in response.body_iterator:
                chunks.append(chunk)
            response_body_bytes = b"".join(chunks)

            # Try to parse response body based on content type
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type:
                try:
                    import json

                    response_body = json.loads(response_body_bytes.decode("utf-8"))
                except Exception:
                    response_body = {
                        "content": response_body_bytes.decode("utf-8", errors="ignore")
                    }
            else:
                # Use the BodyProcessor utility for other content types
                response_body = BodyProcessor.process_body_content(
                    response_body_bytes,
                    content_type,
                    max_size=self.config.request_logging_max_body_size,
                )

            # Create new response with the same body to maintain stream integrity
            new_response = Response(
                content=response_body_bytes,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

            return response_body, new_response

        except Exception as e:
            self.logger.warning(f"failed to capture response body: {e!s}")
            return None, response

    async def _create_request_context(
        self, request: Request, start_datetime: datetime
    ) -> dict[str, Any]:
        """Create comprehensive request context for logging."""

        trace_id = TraceContextExtractor.get_trace_id(request)
        request_id = TraceContextExtractor.get_request_id(request)

        query_params = self._format_params(dict(request.query_params))
        path_params = self._format_params(dict(request.path_params))

        context = {
            "trace_id": trace_id,
            "request_id": request_id,
            "body": await self._safe_get_request_body(request),
            "method": request.method,
            "url": str(request.url),
            "path": request.url.path,
            "path_params": path_params,
            "query_params": query_params,
            "content_type": request.headers.get("content-type"),
            "content_length": self._safe_int(request.headers.get("content-length")),
            "client_ip": ClientIPExtractor.extract_client_ip(request),
            "user_agent": request.headers.get("user-agent"),
            "start_time": start_datetime,
            "event": "request_started",
        }

        # Add sanitized headers if configured
        if self.config.request_logging_log_headers:
            context["headers"] = DataSanitizer.sanitize_headers(dict(request.headers))

        # Add authentication context
        context.update(self._extract_auth_info(request))

        return context

    def _create_response_context(
        self,
        _request: Request,
        response: Response,
        end_datetime: datetime,
        duration: float,
        response_body: Any = None,
    ) -> dict[str, Any]:
        """Create comprehensive response context for logging."""

        context = {
            "duration_ms": round(duration * 1000, 2),
            "end_time": end_datetime,
            "event": "request_completed",
            "response_size": self._safe_int(response.headers.get("content-length")),
            "response_type": response.__class__.__name__,
            "status_code": response.status_code,
            "success": 200 <= response.status_code < 400,
            "response_body": response_body,
        }

        # Add response headers if configured - with hyphen replacement
        if self.config.request_logging_log_headers:
            # Fix the response headers as well
            response_headers = self._format_params(dict(response.headers))
            context["response_headers"] = DataSanitizer.sanitize_headers(
                response_headers
            )

        # Add error categorization for non-2xx responses
        if response.status_code >= 400:
            context.update(self._categorize_error_response(response.status_code))

        return context

    def _extract_auth_info(self, request: Request) -> dict[str, Any]:
        """Extract authentication information safely."""

        auth_info = {
            "auth_method": None,
            "authenticated": False,
            "client_id": None,
            "has_bearer_token": False,
            "scopes": [],
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
                    auth_info["scopes"] = [scope.name for scope in scopes]

        # Check for JWT token presence
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            auth_info["auth_method"] = "jwt_bearer"
            auth_info["has_bearer_token"] = True

        return auth_info

    def _categorize_error_response(self, status_code: int) -> dict[str, Any]:
        """Categorize error responses for analysis."""

        error_categories = {
            400: "bad_request",
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            422: "validation_error",
            429: "rate_limited",
            500: "internal_server_error",
            502: "bad_gateway",
            503: "service_unavailable",
            504: "gateway_timeout",
        }

        category = error_categories.get(status_code)

        if not category:
            if 400 <= status_code < 500:
                category = "client_error"

            elif 500 <= status_code < 600:
                category = "server_error"

            else:
                category = "unknown_error"

        return {
            "error_occurred": True,
            "error_category": category,
            "error_type": f"http_{status_code}",
        }

    async def _submit_database_logging(self, data: dict[str, Any]) -> None:
        """Submit comprehensive logging task for database storage."""

        try:
            # Add metadata
            data.update(
                {
                    "logged_at": datetime.now(di["timezone"]),
                    "request_count": self._request_count,
                    "app_version": getattr(self.config, "app_version", "unknown"),
                }
            )

            # Submit with error handling
            await self.task_manager.submit_task(
                "request_log:create",
                data,
                trace_id=data.get("trace_id"),
                request_id=data.get("request_id"),
            )

        except Exception as e:
            self.logger.bind(
                trace_id=data.get("trace_id"),
                request_id=data.get("request_id"),
                error=str(e),
            ).error("failed to submit request logging task")

    def _should_process_request(self, request: Request) -> bool:
        """Determine if request should be processed for logging."""

        path = request.url.path

        # Skip health check, docs and metrics endpoints
        skip_endpoints = {
            "/v1/health",
            "/v1/metrics",
            "/v1/docs",
            "/v1/redoc",
            "/v1/openapi.json",
            "/v1/favicon.ico",
        }

        if path in skip_endpoints or path.startswith("/static/"):
            return False

        # Check excluded paths from configuration
        excluded_paths = getattr(self.config, "request_logging_excluded_paths", [])
        for excluded_path in excluded_paths:
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
            "total_skipped": self._skip_count,
            "skip_rate": self._skip_count
            / max(self._request_count + self._skip_count, 1),
        }

    def _format_params(self, params: Any) -> dict[str, Any]:
        """Helper to convert hyphens to underscores and return None if empty."""
        if not params:
            return None
        return {k.replace("-", "_"): v for k, v in dict(params).items()}
