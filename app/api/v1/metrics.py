from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST

from app.infrastructure.observability import MetricsAggregator

router = APIRouter(prefix='/metrics', tags=['observability'])


@router.get('')
async def metrics() -> Response:
    aggregator = MetricsAggregator()
    await aggregator.collect_all_metrics()

    return Response(
        content=aggregator.get_prometheus_format(),
        media_type=CONTENT_TYPE_LATEST,
    )
