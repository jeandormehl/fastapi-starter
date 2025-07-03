"""
Lightweight Prometheus middleware for custom metrics (optional).

Not strictly necessary because `prometheus_fastapi_instrumentator`
already generates rich metrics, but retained here to demonstrate
manual exemplar usage.
"""

import time
from collections.abc import Awaitable, Callable

from fastapi.requests import Request
from fastapi.responses import Response
from prometheus_client import Histogram
from starlette.middleware.base import BaseHTTPMiddleware

from app.domain.common.utils import StringUtils

REQUEST_TIME = Histogram(
    name='fastapi_requests_duration_seconds',
    documentation='Histogram of request processing time',
    labelnames=['method', 'route', 'status_code', 'service_name'],
)


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start

        REQUEST_TIME.labels(
            request.method,
            request.url.path,
            response.status_code,
            StringUtils.service_name(),
        ).observe(duration)

        return response
