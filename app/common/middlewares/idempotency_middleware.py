import json
from typing import Any

from fastapi import Request, Response
from kink import di
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from app.common.logging import get_logger
from app.domain.v1.idempotency.services.idempotency_service import IdempotencyService


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Middleware for handling HTTP-level idempotency"""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

        self.logger = get_logger(__name__)
        self.idempotency_service = di[IdempotencyService]

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Process request with optional idempotency checking"""

        # Skip idempotency for non-applicable requests
        if not self._should_apply_idempotency(request):
            return await call_next(request)

        idempotency_key = self._get_idempotency_key(request)
        if not idempotency_key:
            return await call_next(request)

        # Read and store request body for hashing
        body = await request.body()
        request._body = body

        # Generate request hash
        content_hash = self.idempotency_service.generate_request_hash(
            method=request.method,
            path=request.url.path,
            body=body,
            headers=dict(request.headers),
        )

        # Check for duplicate
        idempotency_result = await self.idempotency_service.check_request_idempotency(
            idempotency_key=idempotency_key,
            method=request.method,
            path=request.url.path,
            content_hash=content_hash,
            _client_id=self._get_client_id(request),
        )

        if idempotency_result.is_duplicate and idempotency_result.cached_response:
            # Return cached response
            cached = idempotency_result.cached_response
            response = JSONResponse(
                content=cached["body"],
                status_code=cached["status_code"],
                headers={
                    **cached.get("headers", {}),
                    "X-Idempotency-Replayed": "true",
                    "X-Idempotency-Key": idempotency_key,
                },
            )

            self.logger.info(
                f"returned cached response for idempotency key: {idempotency_key}"
            )
            return response

        # Process new request
        response = await call_next(request)

        # Cache successful responses
        if 200 <= response.status_code < 300:
            await self._cache_response(request, response, idempotency_key, content_hash)

        # Add idempotency headers
        response.headers["X-Idempotency-Key"] = idempotency_key
        response.headers["X-Idempotency-Replayed"] = "false"

        return response

    def _should_apply_idempotency(self, request: Request) -> bool:
        """Check if idempotency should be applied"""

        return self.idempotency_service.should_apply_request_idempotency(
            request.method, request.url.path
        )

    def _get_idempotency_key(self, request: Request) -> str:
        """Extract idempotency key from headers"""

        return self.idempotency_service.extract_idempotency_key(dict(request.headers))

    def _get_client_id(self, request: Request) -> str:
        """Extract client ID from request state"""

        if hasattr(request.state, "client"):
            return getattr(request.state.client, "client_id", None)
        return None

    async def _cache_response(
        self,
        request: Request,
        response: Response,
        idempotency_key: str,
        content_hash: str,
    ) -> None:
        """Cache response for future requests"""

        try:
            # Extract response body
            response_body = {}

            if hasattr(response, "body"):
                body_bytes = response.body
                if body_bytes:
                    response_body = json.loads(body_bytes.decode())

            await self.idempotency_service.cache_request_response(
                idempotency_key=idempotency_key,
                method=request.method,
                path=request.url.path,
                content_hash=content_hash,
                response_status=response.status_code,
                response_body=response_body,
                response_headers=dict(response.headers),
                client_id=self._get_client_id(request),
            )

        except Exception as e:
            self.logger.error(f"failed to cache response: {e}")
