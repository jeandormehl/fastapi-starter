from __future__ import annotations

from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.baggage.propagation import W3CBaggagePropagator
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider, sampling
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from prometheus_client import REGISTRY
from prometheus_fastapi_instrumentator import Instrumentator, metrics

from app.core.logging import get_logger
from app.domain.common.utils import StringUtils

if TYPE_CHECKING:
    from fastapi import FastAPI
    from opentelemetry.sdk.trace.sampling import Sampler

    from app.core.config import Configuration

from opentelemetry.sdk.version import __version__

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
            'service.name': StringUtils.service_name(),
            'service.version': config.app_version,
            'service.namespace': config.app_environment,
            'service.instance.id': (
                f'{StringUtils.service_name()}-{config.app_environment}'
            ),
            'deployment.environment': config.app_environment,
            'telemetry.sdk.name': 'opentelemetry',
            'telemetry.sdk.language': 'python',
            'telemetry.sdk.version': __version__,
        }
    )

    # Create tracer provider
    provider = TracerProvider(
        sampler=sampler,
        resource=resource,
    )

    # OTLP exporter for Tempo
    otlp_exporter = OTLPSpanExporter(
        endpoint=str(config.observability.traces_endpoint),
        insecure=True,
        headers={},
        timeout=30,
    )

    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

    # Add console exporter for development
    if config.observability.traces_to_console:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)

    # Setup propagators for distributed tracing
    set_global_textmap(
        CompositePropagator(
            [
                TraceContextTextMapPropagator(),
                W3CBaggagePropagator(),
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
        should_respect_env_var=True,
        inprogress_name='http_requests_inprogress',
        inprogress_labels=True,
        env_var_name='OBSERVABILITY_ENABLED',
        registry=registry,
    )

    instrumentator.add(
        metrics.combined_size(
            should_include_handler=True,
            should_include_method=True,
            should_include_status=True,
        )
    )

    instrumentator.add(
        metrics.latency(
            should_include_handler=True,
            should_include_method=True,
            should_include_status=True,
        )
    )

    instrumentator.instrument(app)


def _setup_fastapi_instrumentation(app: FastAPI, config: Configuration) -> None:
    """Setup FastAPI-specific instrumentation."""
    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls=config.observability.excluded_urls,
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
