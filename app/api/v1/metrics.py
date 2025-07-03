from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.infrastructure.observability import MetricsAggregator

router = APIRouter(prefix='/metrics', tags=['metrics'])


@router.get('')
async def get_metrics() -> PlainTextResponse:
    metrics = MetricsAggregator()
    await metrics.collect_all_metrics()

    return PlainTextResponse(content=metrics.get_prometheus_format())
