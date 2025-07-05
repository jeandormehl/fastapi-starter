from __future__ import annotations

from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.b3 import B3MultiFormat
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.propagators.jaeger import JaegerPropagator
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider, sampling
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from prometheus_client import REGISTRY
from prometheus_fastapi_instrumentator import Instrumentator

from app.core.logging import get_logger
from app.domain.common.utils import StringUtils

if TYPE_CHECKING:
    from fastapi import FastAPI
    from opentelemetry.sdk.trace.sampling import Sampler

    from app.core.config import Configuration

logger = get_logger(__name__)


# noinspection HttpUrlsUsage
def _setup_tracing(config: Configuration) -> None:
    """Setup distributed tracing with OpenTelemetry."""
    if config.observability.tracing_sample_ratio >= 1.0:
        sampler: Sampler = sampling.ALWAYS_ON

    elif config.observability.tracing_sample_ratio <= 0.0:
        sampler = sampling.ALWAYS_OFF

    else:
        sampler = sampling.TraceIdRatioBased(config.observability.tracing_sample_ratio)

    resource = Resource.create(
        {
            'service.environment': config.app_environment,
            'service.name': StringUtils.service_name(),
            'service.version': config.app_version,
            'service.namespace': config.app_environment,
            'service.instance.id': (
                f'{StringUtils.service_name()}-{config.app_environment}'
            ),
            'deployment.environment': config.app_environment,
        }
    )

    # Create tracer provider
    provider = TracerProvider(
        sampler=sampler,
        resource=resource,
    )

    # Setup span processors
    endpoint = str(config.observability.traces_endpoint)
    if not endpoint.startswith('http'):
        endpoint = f'http://{endpoint}'

    # OTLP exporter for Tempo
    otlp_exporter = OTLPSpanExporter(
        endpoint=endpoint,
        insecure=True,
        headers={},
        timeout=30,
    )

    provider.add_span_processor(
        BatchSpanProcessor(
            otlp_exporter,
            max_queue_size=2048,
            max_export_batch_size=512,
            export_timeout_millis=30000,
            schedule_delay_millis=5000,
        )
    )

    # Add console exporter for development
    if config.app_debug:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)

    # Setup propagators for distributed tracing
    set_global_textmap(
        CompositePropagator(
            [
                JaegerPropagator(),
                B3MultiFormat(),
            ]
        )
    )

    # Instrument libraries
    _instrument_libraries()


def _instrument_libraries() -> None:
    """Instrument common libraries for automatic tracing."""

    # HTTP clients
    HTTPXClientInstrumentor().instrument()

    # Redis
    RedisInstrumentor().instrument()


def _setup_metrics(app: FastAPI) -> None:
    registry = REGISTRY

    instrumentator = Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        should_round_latency_decimals=True,
        should_respect_env_var=True,
        should_instrument_requests_inprogress=True,
        excluded_handlers=[
            '/health',
            '/metrics',
            '/docs',
            '/openapi.json',
            '/redoc',
            '/favicon.ico',
        ],
        env_var_name='OBSERVABILITY_ENABLED',
        registry=registry,
    )

    instrumentator.instrument(app)


def _setup_fastapi_instrumentation(app: FastAPI, config: Configuration) -> None:
    """Setup FastAPI-specific instrumentation."""
    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls=config.observability.excluded_urls,
        tracer_provider=trace.get_tracer_provider(),
        http_capture_headers_server_request=[
            'content-type',
            'user-agent',
            'authorization',
        ],
        http_capture_headers_server_response=[
            'content-type',
            'content-length',
        ],
    )


def configure_observability(app: FastAPI, config: Configuration) -> None:
    """Configure complete observability stack for the application."""
    if not config.observability.enabled:
        return

    # Setup tracing
    _setup_tracing(config)

    # Setup metrics
    _setup_metrics(app)

    # Setup FastAPI instrumentation
    _setup_fastapi_instrumentation(app, config)
