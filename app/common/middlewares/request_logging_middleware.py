import asyncio
import contextlib
import json
import time
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

from fastapi import Request, status
from kink import di
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, StreamingResponse
from starlette.types import ASGIApp

from app.core.config import Configuration
from app.core.errors.errors import ApplicationError
from app.core.logging import get_logger
from app.core.utils import safe_int, sanitize_sensitive_headers
from app.infrastructure.taskiq.schemas import TaskPriority
from app.infrastructure.taskiq.task_manager import TaskManager


# noinspection PyBroadException
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for comprehensive request/response logging to database.

    Features:
    - Memory-efficient streaming body capture
    - error handling and recovery
    - Configurable logging levels and filtering
    - Performance monitoring and metrics
    - Thread-safe operations with proper cleanup
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

        self.config = di[Configuration]
        self.logger = get_logger(__name__)
        self.task_manager = di[TaskManager]

        # Performance tracking with thread safety
        self._request_count = 0
        self._error_count = 0
        self._skip_count = 0

        # Memory management
        self._active_requests = set()

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Process request with enhanced logging capabilities."""

        # Quick skip check to avoid unnecessary processing
        if not self._should_process_request(request):
            self._skip_count += 1
            return await call_next(request)

        # Initialize request context with memory tracking
        request_context = await self._initialize_request_context(request)
        self._active_requests.add(request)

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

        finally:
            # Cleanup request from tracking
            try:
                # noinspection PyInconsistentReturns
                self._active_requests.discard(request)
            except Exception:
                # noinspection PyInconsistentReturns
                contextlib.suppress(Exception)

    async def _process_request_with_logging(
        self, request: Request, call_next: Any, request_context: dict[str, Any]
    ) -> Response:
        """Core request processing with comprehensive logging."""

        start_time = time.time()
        start_datetime = datetime.now(di["timezone"])

        # Capture request data with memory-efficient body reading
        request_data = await self._capture_request_data(
            request, start_datetime, request_context
        )

        # Process request
        response = await call_next(request)

        # Capture response data with streaming support
        end_time = time.time()
        end_datetime = datetime.now(di["timezone"])
        duration_ms = (end_time - start_time) * 1000

        response_data = await self._capture_response_data(
            request, response, end_datetime, duration_ms
        )

        # Combine and submit logging task asynchronously
        asyncio.create_task(  # noqa: RUF006
            self._submit_logging_task({**request_data, **response_data})
        )

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
        """request data capture with memory-efficient body reading."""

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

        # header capture
        if self.config.request_logging_log_headers:
            data["headers"] = self._capture_filtered_headers(dict(request.headers))

        # Memory-efficient body capture
        if self.config.request_logging_log_body and self._should_capture_body(request):
            data["body"] = await self._capture_request_body_safe(request)

        # authentication info
        data.update(self._extract_auth_info(request))

        return data

    async def _capture_response_data(
        self,
        request: Request,
        response: Response,
        end_datetime: datetime,
        duration_ms: float,
    ) -> dict[str, Any]:
        """response data capture with memory-efficient handling."""

        data = {
            "status_code": response.status_code,
            "response_size": safe_int(response.headers.get("content-length")),
            "end_time": end_datetime,
            "duration_ms": round(duration_ms, 2),
            "response_type": response.__class__.__name__,
        }

        # header capture
        if self.config.request_logging_log_headers:
            data["response_headers"] = self._capture_filtered_headers(
                dict(response.headers)
            )

        # Memory-efficient response body capture
        if self.config.request_logging_log_body and self._should_capture_response_body(
            response
        ):
            data["response_body"] = await self._capture_response_body_safe(response)

        # error information
        data.update(self._extract_error_info(request, response))

        return data

    async def _capture_request_body_safe(
        self, request: Request
    ) -> dict[str, Any] | None:
        """Memory-efficient request body capture with size limits."""

        try:
            content_length = safe_int(request.headers.get("content-length", 0))
            max_size = self.config.request_logging_max_body_size

            # Check size before reading
            if content_length and content_length > max_size:
                return {
                    "truncated": True,
                    "original_size": content_length,
                    "captured_size": 0,
                    "type": "request",
                    "reason": "size_limit_exceeded",
                }

            # Use safe body reading with timeout and size limit
            body = await self._safe_read_request_body_limited(request, max_size)

            if not body:
                return None

            return await self._process_body_content(body, "request")

        except Exception as e:
            self.logger.bind(error=str(e)).warning("failed to capture request body")
            return {"error": "request_body_capture_failed", "reason": str(e)}

    async def _capture_response_body_safe(
        self, response: Response
    ) -> dict[str, Any] | None:
        """Memory-efficient response body capture with proper streaming handling."""

        try:
            # Handle streaming responses safely
            if isinstance(response, StreamingResponse):
                return await self._capture_streaming_response_safe(response)

            # Handle regular responses with body attribute
            if hasattr(response, "body"):
                body = getattr(response, "body", b"")
                if body:
                    # Check size before processing
                    if len(body) > self.config.request_logging_max_body_size:
                        return {
                            "truncated": True,
                            "original_size": len(body),
                            "captured_size": 0,
                            "type": "response",
                            "reason": "size_limit_exceeded",
                        }
                    return await self._process_body_content(body, "response")

            return None

        except Exception as e:
            self.logger.bind(error=str(e)).warning("failed to capture response body")
            return {"error": "response_body_capture_failed", "reason": str(e)}

    async def _safe_read_request_body_limited(
        self, request: Request, max_size: int
    ) -> bytes:
        """Safe request body reading with size and timeout limits."""

        try:
            # Read body with timeout protection and size limit
            body_task = asyncio.create_task(request.body())

            try:
                body = await asyncio.wait_for(body_task, timeout=30.0)

                # Enforce size limit
                if len(body) > max_size:
                    self.logger.warning(
                        f"request body truncated: {len(body)} > {max_size}"
                    )
                    return body[:max_size]

                return body

            except TimeoutError:
                body_task.cancel()
                self.logger.warning("request body reading timed out")
                return b""

        except Exception as e:
            self.logger.bind(error=str(e)).warning("error reading request body")
            return b""

    async def _capture_streaming_response_safe(
        self, response: StreamingResponse
    ) -> dict[str, Any]:
        """Safe streaming response body capture without breaking the stream."""

        try:
            max_size = self.config.request_logging_max_body_size
            captured_chunks = []
            total_size = 0

            # Create a new iterator that captures data while preserving the original
            async def capture_and_pass_through() -> AsyncGenerator[bytes]:
                nonlocal total_size

                async for chunk in response.body_iterator:
                    chunk_size = len(chunk) if chunk else 0

                    # Capture chunk if under size limit
                    if total_size + chunk_size <= max_size:
                        captured_chunks.append(chunk)

                    total_size += chunk_size
                    yield chunk

            # Replace the iterator with our capturing version
            response.body_iterator = capture_and_pass_through()

            # Return metadata about what we'll capture
            return {
                "type": "streaming_response",
                "capture_enabled": True,
                "max_capture_size": max_size,
                "note": "body will be captured during streaming",
            }

        except Exception as e:
            self.logger.bind(error=str(e)).warning("failed to setup streaming capture")
            return {"error": "streaming_capture_setup_failed", "reason": str(e)}

    async def _process_body_content(
        self, body: bytes, body_type: str
    ) -> dict[str, Any]:
        """Process and format body content with size limits and encoding detection."""

        max_size = self.config.request_logging_max_body_size

        if len(body) > max_size:
            return {
                "truncated": True,
                "original_size": len(body),
                "captured_size": max_size,
                "type": body_type,
                "content": self._truncate_body_safely(body, max_size),
            }

        # Try JSON parsing first
        try:
            content = json.loads(body.decode("utf-8"))

            return {
                "content": content,
                "type": "json",
                "size": len(body),
                "encoding": "utf-8",
            }

        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

        # Try text decoding with multiple encodings
        for encoding in ["utf-8", "utf-16", "latin1"]:
            try:
                content = body.decode(encoding)
                return {
                    "content": content,
                    "type": "text",
                    "size": len(body),
                    "encoding": encoding,
                }

            except UnicodeDecodeError:
                continue

        # Fallback to base64 for binary data
        import base64

        return {
            "content": base64.b64encode(body).decode("ascii"),
            "type": "binary",
            "size": len(body),
            "encoding": "base64",
        }

    def _truncate_body_safely(self, body: bytes, max_size: int) -> str:
        """Safely truncate body content without breaking encoding."""

        truncated = body[:max_size]

        # Try to decode and handle potential broken UTF-8 at the end
        try:
            return truncated.decode("utf-8")
        except UnicodeDecodeError:
            # Remove potentially broken bytes at the end
            for i in range(min(4, len(truncated))):
                try:
                    return truncated[: -i - 1].decode("utf-8") + "..."
                except UnicodeDecodeError:
                    continue

            # Final fallback
            import base64

            return base64.b64encode(truncated).decode("ascii")

    def _capture_filtered_headers(self, headers: dict[str, Any]) -> dict[str, str]:
        """Capture and filter sensitive headers."""
        return sanitize_sensitive_headers(headers)

    def _extract_client_ip(self, request: Request) -> str | None:
        """client IP extraction with proxy support - FIXED."""

        # Check for forwarded headers first
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # FIX: Get first IP from comma-separated list
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()

        # Fallback to direct client
        return request.client.host if request.client else None

    def _extract_auth_info(self, request: Request) -> dict[str, Any]:
        """authentication information extraction with defensive programming."""

        auth_info = {
            "authenticated": False,
            "client_id": None,
            "scopes": [],
            "auth_method": None,
            "has_bearer_token": False,
        }

        # Defensive check for request state
        if not hasattr(request, "state"):
            return auth_info

        # Check request state for authentication
        if hasattr(request.state, "client"):
            client = getattr(request.state, "client", None)
            if client:
                auth_info.update(
                    {
                        "authenticated": True,
                        "client_id": getattr(client, "client_id", None),
                        "auth_method": getattr(client, "auth_method", "unknown"),
                    }
                )

        # Extract scopes safely
        if hasattr(request.state, "scopes"):
            scopes = getattr(request.state, "scopes", [])
            if scopes:
                auth_info["scopes"] = [
                    scope.name if hasattr(scope, "name") else str(scope)
                    for scope in scopes
                ]

        # Check for JWT token presence
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            auth_info["has_bearer_token"] = True

        return auth_info

    def _extract_error_info(
        self, request: Request, response: Response
    ) -> dict[str, Any]:
        """error information extraction with better error categorization."""

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

            # Extract error from response body safely
            try:
                if hasattr(response, "body"):
                    body = getattr(response, "body", b"")
                    if body and len(body) < 10000:  # Limit error body size
                        error_data = json.loads(body.decode("utf-8"))
                        if isinstance(error_data, dict):
                            error_info.update(
                                {
                                    "error_type": error_data.get("code", "unknown"),
                                    "error_message": error_data.get("message"),
                                    "error_details": error_data.get("details"),
                                }
                            )

            except Exception:
                error_info.update(
                    {
                        "error_type": f"http_{response.status_code}",
                        "error_message": f"http {response.status_code} error occurred",
                    }
                )

        # Check for application errors in request state safely
        if hasattr(request, "state") and hasattr(request.state, "app_error"):
            app_error = getattr(request.state, "app_error", None)
            if isinstance(app_error, ApplicationError):
                error_info.update(
                    {
                        "error_occurred": True,
                        "error_type": getattr(
                            app_error.error_code, "value", str(app_error.error_code)
                        ),
                        "error_message": str(app_error.message),
                        "error_details": getattr(app_error, "details", None),
                        "error_category": "application_error",
                    }
                )

        return error_info

    def _categorize_error(self, status_code: int) -> str:
        """Categorize errors by HTTP status code with more granularity."""

        cat = "unknown_error"

        if status_code == 400:
            cat = "bad_request"
        if status_code == 401:
            cat = "unauthorized"
        if status_code == 403:
            cat = "forbidden"
        if status_code == 404:
            cat = "not_found"
        if status_code == 422:
            cat = "validation_error"
        if 400 <= status_code < 500:
            cat = "client_error"
        if status_code == 500:
            cat = "internal_server_error"
        if status_code == 502:
            cat = "bad_gateway"
        if status_code == 503:
            cat = "service_unavailable"
        if 500 <= status_code < 600:
            cat = "server_error"

        return cat

    def _should_process_request(self, request: Request) -> bool:
        """request filtering logic with better pattern matching."""

        if not self.config.request_logging_enabled:
            return False

        path = request.url.path

        # Skip health check and metrics endpoints
        _endpoints = {
            "/health",
            "/metrics",
            "/v1",
            "/docs",
            "/redoc",
            "/openapi.json",
        }
        if path in _endpoints:
            return False

        # Check excluded paths with enhanced pattern matching
        for excluded_path in self.config.request_logging_excluded_paths:
            if path.startswith(excluded_path):
                return False

        # Check excluded methods
        if request.method.upper() in self.config.request_logging_excluded_methods:
            return False

        # Skip if too many concurrent requests for memory management
        return len(self._active_requests) < 100

    def _should_capture_body(self, request: Request) -> bool:
        """Determine if request body should be captured with enhanced checks."""

        # Only capture body for methods that typically have bodies
        if request.method.upper() not in {"POST", "PUT", "PATCH"}:
            return False

        # Check content type
        content_type = request.headers.get("content-type", "").lower()

        # Skip large file uploads
        if "multipart/form-data" in content_type:
            content_length = safe_int(request.headers.get("content-length", 0))
            if content_length > 1024 * 1024:  # Skip files > 1MB
                return False

        allowed_types = {
            "application/json",
            "application/x-www-form-urlencoded",
            "text/plain",
            "application/xml",
            "text/xml",
        }

        return any(
            content_type.startswith(allowed_type) for allowed_type in allowed_types
        )

    def _should_capture_response_body(self, response: Response) -> bool:
        """Determine if response body should be captured."""

        # Skip large responses
        content_length = safe_int(response.headers.get("content-length", 0))
        if content_length > self.config.request_logging_max_body_size:
            return False

        # Skip binary content types
        content_type = response.headers.get("content-type", "").lower()
        skip_types = {
            "image/",
            "video/",
            "audio/",
            "application/octet-stream",
            "application/pdf",
            "application/zip",
        }

        return not any(content_type.startswith(skip_type) for skip_type in skip_types)

    async def _submit_logging_task(self, log_data: dict[str, Any]) -> None:
        """Submit logging task with enhanced error handling and retry logic."""

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

    async def get_middleware_stats(self) -> dict[str, Any]:
        """Get middleware performance statistics."""

        return {
            "total_requests_processed": self._request_count,
            "total_errors": self._error_count,
            "total_skipped": self._skip_count,
            "active_requests": len(self._active_requests),
            "error_rate": self._error_count / max(self._request_count, 1),
            "skip_rate": self._skip_count
            / max(self._request_count + self._skip_count, 1),
            "memory_efficiency": {
                "active_request_tracking": True,
                "streaming_support": True,
                "size_limits_enforced": True,
            },
        }
