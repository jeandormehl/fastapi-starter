import asyncio
import json
import time
from datetime import datetime
from typing import Any

from fastapi import Request, status
from kink import di
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.config import Configuration
from app.core.errors.errors import ApplicationError
from app.core.logging import get_logger
from app.core.utils import safe_int, sanitize_sensitive_headers
from app.infrastructure.taskiq.schemas import TaskPriority
from app.infrastructure.taskiq.task_manager import TaskManager


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for comprehensive request/response logging to database.
    Runs after error middleware to capture error information.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

        self.config = di[Configuration]
        self.logger = get_logger(__name__)
        self.task_manager = di[TaskManager]

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Process request with comprehensive logging."""

        # Skip if request logging is disabled
        if not self.config.request_logging_enabled:
            return await call_next(request)

        # Skip if path is excluded
        if self._should_skip_logging(request):
            return await call_next(request)

        # Capture request start time
        start_time = time.time()
        start_datetime = datetime.now(di["timezone"])

        # Capture request data
        request_data = await self._capture_request_data(request, start_datetime)

        # Process request
        response = await call_next(request)

        # Capture response data and timing
        end_time = time.time()
        end_datetime = datetime.now(di["timezone"])
        duration_ms = (end_time - start_time) * 1000

        response_data = await self._capture_response_data(
            request, response, end_datetime, duration_ms
        )

        # Combine request and response data
        log_data = {**request_data, **response_data}

        # Queue logging task asynchronously
        try:
            asyncio.create_task(  # noqa: RUF006
                self.task_manager.submit_task(
                    "request_log:create", log_data, priority=TaskPriority.LOW
                )
            )
        except Exception as e:
            self.logger.bind(
                trace_id=request_data.get("trace_id"),
                request_id=request_data.get("request_id"),
                error=str(e),
            ).error("failed to queue request logging task")

        return response

    def _should_skip_logging(self, request: Request) -> bool:
        """Determine if request should be skipped from logging."""

        # Ignore docs path
        if request.url.path == "/v1":
            return True

        # Check excluded paths
        for excluded_path in self.config.request_logging_excluded_paths:
            if request.url.path.startswith(excluded_path):
                return True

        # Check excluded methods
        return request.method.upper() in self.config.request_logging_excluded_methods

    async def _capture_request_data(
        self, request: Request, start_datetime: datetime
    ) -> dict[str, Any]:
        """Capture comprehensive request data."""

        # Basic request information
        data = {
            "trace_id": getattr(request.state, "trace_id", "unknown"),
            "request_id": getattr(request.state, "request_id", "unknown"),
            "method": request.method,
            "url": str(request.url),
            "path": request.url.path,
            "query_params": str(request.query_params) if request.query_params else None,
            "content_type": request.headers.get("content-type"),
            "content_length": safe_int(request.headers.get("content-length")),
            "client_ip": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
            "start_time": start_datetime,
        }

        # Capture headers if enabled
        if self.config.request_logging_log_headers:
            # Filter sensitive headers
            filtered_headers = sanitize_sensitive_headers(dict(request.headers))
            data["headers"] = filtered_headers

        # Capture request body if enabled
        if self.config.request_logging_log_body:
            data["body"] = await self._capture_request_body(request)

        # Extract authentication information
        data.update(self._extract_auth_info(request))

        return data

    async def _capture_response_data(
        self,
        request: Request,
        response: Response,
        end_datetime: datetime,
        duration_ms: float,
    ) -> dict[str, Any]:
        """Capture comprehensive response data."""

        data = {
            "status_code": response.status_code,
            "response_size": safe_int(response.headers.get("content-length")),
            "end_time": end_datetime,
            "duration_ms": round(duration_ms, 2),
        }

        # Capture response headers if enabled
        if self.config.request_logging_log_headers:
            filtered_headers = sanitize_sensitive_headers(dict(response.headers))
            data["response_headers"] = filtered_headers

        # Capture response body if enabled
        if self.config.request_logging_log_body:
            data["response_body"] = await self._capture_response_body(response)

        # Check for error information
        error_info = self._extract_error_info(request, response)
        data.update(error_info)

        return data

    async def _capture_request_body(self, request: Request) -> dict[str, Any] | None:
        """Safely capture and parse request body."""

        try:
            # Get body size limit
            max_size = self.config.request_logging_max_body_size

            # Read body (this might fail if already consumed)
            body = await request.body()

            if len(body) > max_size:
                return {"truncated": True, "original_size": len(body)}

            if not body:
                return None

            # Try to parse as JSON
            try:
                return json.loads(body.decode("utf-8"))

            except (json.JSONDecodeError, UnicodeDecodeError):
                # Return as base64 encoded string for binary data
                import base64

                return {
                    "type": "binary",
                    "data": base64.b64encode(body).decode("ascii"),
                    "size": len(body),
                }

        except Exception as e:
            self.logger.bind(error=str(e)).warning("failed to capture request body")
            return {"error": "failed to capture body"}

    async def _capture_response_body(self, response: Response) -> dict[str, Any] | None:
        """Safely capture and parse response body."""

        try:
            # Check if response has body attribute (StreamingResponse might not)
            if not hasattr(response, "body"):
                return {
                    "type": "streaming",
                    "note": "streaming response body not captured",
                }

            body = getattr(response, "body", b"")
            if not body:
                return None

            max_size = self.config.request_logging_max_body_size
            if len(body) > max_size:
                return {"truncated": True, "original_size": len(body)}

            # Try to parse as JSON
            try:
                return json.loads(body.decode("utf-8"))

            except (json.JSONDecodeError, UnicodeDecodeError):
                # Return as base64 encoded string for binary data
                import base64

                return {
                    "type": "binary",
                    "data": base64.b64encode(body).decode("ascii"),
                    "size": len(body),
                }

        except Exception as e:
            self.logger.bind(error=str(e)).warning("failed to capture response body")
            return {"error": "failed to capture response body"}

    def _extract_auth_info(self, request: Request) -> dict[str, Any]:
        """Extract authentication and authorization information."""

        auth_info = {
            "authenticated": False,
            "client_id": None,
            "scopes": [],
        }

        # Check for authentication information in request state
        if hasattr(request.state, "client"):
            client = request.state.client
            if client:
                auth_info["authenticated"] = True
                auth_info["client_id"] = getattr(client, "client_id", None)

        # Extract scopes if available
        if hasattr(request.state, "scopes"):
            scopes = getattr(request.state, "scopes", [])
            auth_info["scopes"] = [scope.name for scope in scopes]

        return auth_info

    def _extract_error_info(
        self, request: Request, response: Response
    ) -> dict[str, Any]:
        """Extract error information from response."""

        error_info = {
            "error_occurred": False,
            "error_type": None,
            "error_message": None,
            "error_details": None,
        }

        # Check if response indicates an error
        if response.status_code >= status.HTTP_400_BAD_REQUEST:
            error_info["error_occurred"] = True

            # Try to extract error details from response body
            try:
                body = getattr(response, "body", b"")
                if body:
                    error_data = json.loads(body.decode("utf-8"))

                    # Check if it's an ErrorDetail format
                    if isinstance(error_data, dict):
                        error_info["error_type"] = error_data.get("code")
                        error_info["error_message"] = error_data.get("message")
                        error_info["error_details"] = error_data.get("details")

            except Exception as e:
                # Fallback to generic error information
                error_info["error_type"] = f"{type(e)}"
                error_info["error_message"] = f"http error has occurred: {e!s}"

        # Check for error information stored in request state
        if hasattr(request.state, "app_error"):
            app_error = request.state.app_error
            if isinstance(app_error, ApplicationError):
                error_info.update(
                    {
                        "error_occurred": True,
                        "error_type": app_error.error_code.value,
                        "error_message": app_error.message,
                        "error_details": app_error.details,
                    }
                )

        return error_info
