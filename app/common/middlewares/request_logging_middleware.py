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

    Features:
    - Optimized body reading to prevent request hanging
    - Enhanced error handling and recovery
    - Configurable logging levels and filtering
    - Performance monitoring and metrics
    - Thread-safe operations
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
        """Process request with enhanced logging capabilities."""

        # Quick skip check to avoid unnecessary processing
        if not self._should_process_request(request):
            self._skip_count += 1
            return await call_next(request)

        # Initialize request context
        request_context = await self._initialize_request_context(request)

        try:
            # Process request with enhanced error handling
            response = await self._process_request_with_logging(
                request, call_next, request_context
            )
            self._request_count += 1
            return response

        except Exception as exc:
            self._error_count += 1
            self.logger.bind(
                trace_id=request_context.get("trace_id"),
                request_id=request_context.get("request_id"),
                error=str(exc),
            ).error("critical error in request logging middleware")

            # Fallback: continue request processing even if logging fails
            return await call_next(request)

    async def _process_request_with_logging(
        self, request: Request, call_next: Any, request_context: dict[str, Any]
    ) -> Response:
        """Core request processing with comprehensive logging."""

        start_time = time.time()
        start_datetime = datetime.now(di["timezone"])

        # Capture request data with optimized body reading
        request_data = await self._capture_request_data(
            request, start_datetime, request_context
        )

        # Process request
        response = await call_next(request)

        # Capture response data
        end_time = time.time()
        end_datetime = datetime.now(di["timezone"])
        duration_ms = (end_time - start_time) * 1000

        response_data = await self._capture_response_data(
            request, response, end_datetime, duration_ms
        )

        # Combine and submit logging task
        await self._submit_logging_task({**request_data, **response_data})

        return response

    async def _initialize_request_context(self, request: Request) -> dict[str, Any]:
        """Initialize request context with enhanced error handling."""

        return {
            "trace_id": getattr(request.state, "trace_id", "unknown"),
            "request_id": getattr(request.state, "request_id", "unknown"),
            "start_time": time.time(),
        }

    async def _capture_request_data(
        self, request: Request, start_datetime: datetime, context: dict[str, Any]
    ) -> dict[str, Any]:
        """Enhanced request data capture with optimized body reading."""

        # Basic request information
        data = {
            "trace_id": context["trace_id"],
            "request_id": context["request_id"],
            "method": request.method,
            "url": str(request.url),
            "path": request.url.path,
            "query_params": str(request.query_params) if request.query_params else None,
            "content_type": request.headers.get("content-type"),
            "content_length": safe_int(request.headers.get("content-length")),
            "client_ip": self._extract_client_ip(request),
            "user_agent": request.headers.get("user-agent"),
            "start_time": start_datetime,
        }

        # Enhanced header capture
        if self.config.request_logging_log_headers:
            data["headers"] = await self._capture_filtered_headers(request.headers)

        # Optimized body capture
        if self.config.request_logging_log_body and self._should_capture_body(request):
            data["body"] = await self._capture_request_body(request)

        # Enhanced authentication info
        data.update(self._extract_enhanced_auth_info(request))

        return data

    async def _capture_response_data(
        self,
        request: Request,
        response: Response,
        end_datetime: datetime,
        duration_ms: float,
    ) -> dict[str, Any]:
        """Enhanced response data capture with better error handling."""

        data = {
            "status_code": response.status_code,
            "response_size": safe_int(response.headers.get("content-length")),
            "end_time": end_datetime,
            "duration_ms": round(duration_ms, 2),
            "response_type": response.__class__.__name__,
        }

        # Enhanced header capture
        if self.config.request_logging_log_headers:
            data["response_headers"] = await self._capture_filtered_headers(
                response.headers
            )

        # Optimized response body capture
        if self.config.request_logging_log_body:
            data["response_body"] = await self._capture_optimized_response_body(
                response
            )

        # Enhanced error information
        data.update(self._extract_error_info(request, response))

        return data

    async def _capture_request_body(self, request: Request) -> dict[str, Any] | None:
        """Optimized request body capture preventing hanging issues."""

        try:
            # Use safe body reading method to prevent hanging
            body = await self._safe_read_request_body(request)

            if not body:
                return None

            return await self._process_body_content(body, "request")

        except Exception as e:
            self.logger.bind(error=str(e)).warning("failed to capture request body")
            return {"error": "request_body_capture_failed", "reason": str(e)}

    async def _capture_optimized_response_body(
        self, response: Response
    ) -> dict[str, Any] | None:
        """Optimized response body capture with streaming support."""

        try:
            # Handle different response types
            if hasattr(response, "body"):
                body = getattr(response, "body", b"")
                if body:
                    return await self._process_body_content(body, "response")

            # Handle streaming responses
            if hasattr(response, "body_iterator"):
                return await self._capture_streaming_response_body(response)

            return None

        except Exception as e:
            self.logger.bind(error=str(e)).warning("failed to capture response body")
            return {"error": "response_body_capture_failed", "reason": str(e)}

    async def _safe_read_request_body(self, request: Request) -> bytes:
        """Safe request body reading to prevent hanging issues."""

        try:
            # Read body with timeout protection
            return await asyncio.wait_for(request.body(), timeout=10.0)

        except TimeoutError:
            self.logger.warning("request body reading timed out")
            return b""

        except Exception as e:
            self.logger.bind(error=str(e)).warning("error reading request body")
            return b""

    async def _capture_streaming_response_body(
        self, response: Response
    ) -> dict[str, Any]:
        """Handle streaming response body capture."""

        try:
            body_chunks = []
            total_size = 0
            max_size = self.config.request_logging_max_body_size

            async for chunk in response.body_iterator:
                total_size += len(chunk)

                if total_size > max_size:
                    return {
                        "type": "streaming_truncated",
                        "captured_size": len(b"".join(body_chunks)),
                        "total_size": total_size,
                    }

                body_chunks.append(chunk)

            # Restore iterator for actual response
            from starlette.concurrency import iterate_in_threadpool

            response.body_iterator = iterate_in_threadpool(iter(body_chunks))

            # Process captured content
            full_body = b"".join(body_chunks)
            return await self._process_body_content(full_body, "streaming_response")

        except Exception as e:
            self.logger.bind(error=str(e)).warning(
                "failed to capture streaming response"
            )

            return {"error": "streaming_capture_failed", "reason": str(e)}

    async def _process_body_content(
        self, body: bytes, body_type: str
    ) -> dict[str, Any]:
        """Process and format body content with size limits."""

        max_size = self.config.request_logging_max_body_size

        if len(body) > max_size:
            return {
                "truncated": True,
                "original_size": len(body),
                "captured_size": max_size,
                "type": body_type,
            }

        # Try JSON parsing first
        try:
            return {
                "content": json.loads(body.decode("utf-8")),
                "type": "json",
                "size": len(body),
            }

        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

        # Try text decoding
        try:
            return {"content": body.decode("utf-8"), "type": "text", "size": len(body)}

        except UnicodeDecodeError:
            pass

        # Fallback to base64 for binary data
        import base64

        return {
            "content": base64.b64encode(body).decode("ascii"),
            "type": "binary",
            "size": len(body),
        }

    async def _capture_filtered_headers(
        self, headers: dict[str, Any]
    ) -> dict[str, str]:
        """Capture and filter sensitive headers."""

        return sanitize_sensitive_headers(dict(headers))

    def _extract_client_ip(self, request: Request) -> str | None:
        """Enhanced client IP extraction with proxy support."""

        # Check for forwarded headers first
        forwarded_for = request.headers.get("x-forwarded-for")

        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()

        # Fallback to direct client
        return request.client.host if request.client else None

    def _extract_enhanced_auth_info(self, request: Request) -> dict[str, Any]:
        """Enhanced authentication information extraction."""

        auth_info = {
            "authenticated": False,
            "client_id": None,
            "scopes": [],
            "auth_method": None,
        }

        # Check request state for authentication
        if hasattr(request.state, "client"):
            client = request.state.client
            if client:
                auth_info.update(
                    {
                        "authenticated": True,
                        "client_id": getattr(client, "client_id", None),
                        "auth_method": getattr(client, "auth_method", "unknown"),
                    }
                )

        # Extract scopes
        if hasattr(request.state, "scopes"):
            scopes = getattr(request.state, "scopes", [])
            auth_info["scopes"] = [
                scope.name if hasattr(scope, "name") else str(scope) for scope in scopes
            ]

        # Check for JWT token presence
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            auth_info["has_bearer_token"] = True

        return auth_info

    def _extract_error_info(
        self, request: Request, response: Response
    ) -> dict[str, Any]:
        """Enhanced error information extraction."""

        error_info = {
            "error_occurred": False,
            "error_type": None,
            "error_message": None,
            "error_details": None,
            "error_category": None,
        }

        # Categorize errors by status code
        if response.status_code >= status.HTTP_400_BAD_REQUEST:
            error_info["error_occurred"] = True
            error_info["error_category"] = self._categorize_error(response.status_code)

            # Extract error from response body
            try:
                body = getattr(response, "body", b"")
                if body:
                    error_data = json.loads(body.decode("utf-8"))
                    if isinstance(error_data, dict):
                        error_info.update(
                            {
                                "error_type": error_data.get("code", "unknown"),
                                "error_message": error_data.get("message"),
                                "error_details": error_data.get("details"),
                            }
                        )

            except Exception as e:
                error_info.update(
                    {
                        "error_type": f"http_{response.status_code}",
                        "error_message": f"http {response.status_code} error occurred: "
                        f"{e!s}",
                    }
                )

        # Check for application errors in request state
        if hasattr(request.state, "app_error"):
            app_error = request.state.app_error
            if isinstance(app_error, ApplicationError):
                error_info.update(
                    {
                        "error_occurred": True,
                        "error_type": app_error.error_code.value,
                        "error_message": app_error.message,
                        "error_details": app_error.details,
                        "error_category": "application_error",
                    }
                )

        return error_info

    def _categorize_error(self, status_code: int) -> str:
        """Categorize errors by HTTP status code."""

        if 400 <= status_code < 500:
            return "client_error"
        if 500 <= status_code < 600:
            return "server_error"
        return "unknown_error"

    def _should_process_request(self, request: Request) -> bool:
        """Enhanced request filtering logic."""

        if not self.config.request_logging_enabled:
            return False

        # Skip health check and metrics endpoints
        if request.url.path in ["/health", "/metrics", "/v1"]:
            return False

        # Check excluded paths with enhanced pattern matching
        for excluded_path in self.config.request_logging_excluded_paths:
            if request.url.path.startswith(excluded_path):
                return False

        # Check excluded methods
        return (
            request.method.upper() not in self.config.request_logging_excluded_methods
        )

    def _should_capture_body(self, request: Request) -> bool:
        """Determine if request body should be captured."""

        # Only capture body for methods that typically have bodies
        if request.method.upper() not in ["POST", "PUT", "PATCH"]:
            return False

        # Check content type
        content_type = request.headers.get("content-type", "")
        allowed_types = [
            "application/json",
            "application/x-www-form-urlencoded",
            "text/plain",
        ]

        return any(
            content_type.startswith(allowed_type) for allowed_type in allowed_types
        )

    async def _submit_logging_task(self, log_data: dict[str, Any]) -> None:
        """Submit logging task with enhanced error handling."""

        try:
            # Add metadata
            log_data.update(
                {
                    "logged_at": datetime.now(di["timezone"]),
                    "middleware_version": "2.0.0",
                    "request_count": self._request_count,
                }
            )

            # Submit with retry capability
            await self.task_manager.submit_task(
                "request_log:create", log_data, priority=TaskPriority.LOW, max_retries=3
            )

        except Exception as e:
            self.logger.bind(
                trace_id=log_data.get("trace_id"),
                request_id=log_data.get("request_id"),
                error=str(e),
            ).error("failed to submit request logging task")

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
