from __future__ import annotations

from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider, sampling
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_fastapi_instrumentator import Instrumentator

from app.core.logging import get_logger
from app.domain.common.utils import StringUtils

if TYPE_CHECKING:
    from fastapi import FastAPI

    from app.core.config import Configuration

logger = get_logger(__name__)


def _setup_tracing(config: Configuration) -> None:
    sampler = (
        sampling.ALWAYS_ON
        if config.observability.tracing_sample_ratio >= 1.0
        else sampling.TraceIdRatioBased(config.observability.tracing_sample_ratio)
    )

    provider = TracerProvider(
        sampler=sampler,
        resource=Resource.create(
            {
                'service.environment': config.app_environment,
                'service.name': StringUtils.service_name(),
                'service.version': config.app_version,
            }
        ),
    )

    endpoint = (
        f'{config.observability.traces_endpoint.host}:'
        f'{config.observability.traces_endpoint.port!s}'
    )
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )
    trace.set_tracer_provider(provider)

    # Instrument libraries
    HTTPXClientInstrumentor().instrument()
    RedisInstrumentor().instrument()


def _setup_metrics(app: FastAPI) -> None:
    Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        excluded_handlers=['/health/liveness', '/metrics'],
        env_var_name='OBSERVABILITY_ENABLED',
    ).instrument(app)


def configure_observability(app: FastAPI, config: Configuration) -> None:
    if not config.observability.enabled:
        return

    _setup_tracing(config)
    _setup_metrics(app)

    FastAPIInstrumentor.instrument_app(
        app, excluded_urls=config.observability.excluded_urls
    )
