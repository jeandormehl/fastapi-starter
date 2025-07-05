from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response
from kink import di

from app.infrastructure.observability import MetricsAggregator

router = APIRouter(prefix='/metrics', tags=['observability'])


@router.get('')
async def get_metrics() -> Response:
    """Get all metrics in Prometheus format."""
    aggregator = di[MetricsAggregator]
    await aggregator.collect_all_metrics()
    metrics_data = aggregator.get_prometheus_format()

    return Response(
        content=metrics_data, media_type='text/plain; version=0.0.4; charset=utf-8'
    )


@router.get('/health')
async def get_health_metrics() -> dict[str, Any]:
    """Get health summary for monitoring."""
    aggregator = di[MetricsAggregator]

    return aggregator.get_health_summary()


@router.get('/prisma')
async def get_prisma_analysis() -> dict[str, Any]:
    """Get detailed Prisma performance analysis."""
    aggregator = di[MetricsAggregator]

    return aggregator.get_prisma_analysis()
