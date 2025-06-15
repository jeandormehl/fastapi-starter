from kink import di
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import (
    DEPLOYMENT_ENVIRONMENT,
    SERVICE_NAME,
    SERVICE_NAMESPACE,
    SERVICE_VERSION,
    Resource,
)
from opentelemetry.sdk.trace import TracerProvider, sampling
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.common.logging import get_logger
from app.core.config import Configuration
from app.core.config.otel_config import OtelConfiguration


def create_resource(config: OtelConfiguration) -> Resource:
    """Create OpenTelemetry resource with service information."""

    resource_attributes = {
        SERVICE_NAME: config.service_name,
        SERVICE_VERSION: config.service_version,
        SERVICE_NAMESPACE: config.service_namespace,
        DEPLOYMENT_ENVIRONMENT: config.service_namespace,
    }

    if config.detect_resource:
        # Add automatic resource detection
        from opentelemetry.sdk.resources import get_aggregated_resources

        return get_aggregated_resources([Resource.create(resource_attributes)])

    return Resource.create(resource_attributes)


def setup_tracing(
    config: OtelConfiguration, resource: Resource
) -> TracerProvider | None:
    """Setup OpenTelemetry tracing."""

    if not config.traces_enabled:
        return None

    # Create sampler based on sample rate
    if config.traces_sample_rate == 1.0:
        sampler = sampling.ALWAYS_ON

    elif config.traces_sample_rate == 0.0:
        sampler = sampling.ALWAYS_OFF

    else:
        sampler = sampling.TraceIdRatioBased(config.traces_sample_rate)

    # Create tracer provider
    tracer_provider = TracerProvider(resource=resource, sampler=sampler)

    # Create OTLP exporter
    otlp_exporter = OTLPSpanExporter(
        endpoint=config.exporter_otlp_endpoint,
        headers=dict(config.exporter_otlp_headers.get_secret_value().split(","))
        if config.exporter_otlp_headers
        else None,
        timeout=config.exporter_otlp_timeout,
        compression=config.exporter_otlp_compression,
    )

    # Add span processor
    span_processor = BatchSpanProcessor(otlp_exporter)
    tracer_provider.add_span_processor(span_processor)

    # Set global tracer provider
    trace.set_tracer_provider(tracer_provider)
    get_logger(__name__).info("otel tracing initialized")

    return tracer_provider


def setup_metrics(
    config: OtelConfiguration, resource: Resource
) -> MeterProvider | None:
    """Setup OpenTelemetry metrics."""

    if not config.metrics_enabled:
        return None

    # Create OTLP metric exporter
    otlp_exporter = OTLPMetricExporter(
        endpoint=config.exporter_otlp_endpoint,
        headers=dict(config.exporter_otlp_headers.get_secret_value().split(","))
        if config.exporter_otlp_headers
        else None,
        timeout=config.exporter_otlp_timeout,
        compression=config.exporter_otlp_compression,
    )

    # Create metric reader
    metric_reader = PeriodicExportingMetricReader(
        exporter=otlp_exporter,
        export_interval_millis=config.metrics_export_interval * 1000,
    )

    # Create meter provider
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])

    # Set global meter provider
    metrics.set_meter_provider(meter_provider)
    get_logger(__name__).info("otel metrics initialized")

    return meter_provider


def initialize_otel() -> tuple[TracerProvider | None, MeterProvider | None]:
    """Initialize OpenTelemetry with middleware integration."""

    config = di[Configuration].otel
    logger = get_logger(__name__)

    if not config.enabled:
        logger.info("otel disabled by configuration")
        return None, None

    try:
        # Create resource
        resource = create_resource(config)

        # Setup tracing and metrics
        tracer_provider = setup_tracing(config, resource)
        meter_provider = setup_metrics(config, resource)

        # Set up context propagation for FastAPI middleware
        from opentelemetry.propagate import set_global_textmap
        from opentelemetry.propagators.b3 import B3MultiFormat
        from opentelemetry.propagators.composite import CompositePropagator
        from opentelemetry.propagators.jaeger import JaegerPropagator
        from opentelemetry.trace.propagation.tracecontext import (
            TraceContextTextMapPropagator,
        )

        # Configure propagators
        set_global_textmap(
            CompositePropagator(
                [TraceContextTextMapPropagator(), B3MultiFormat(), JaegerPropagator()]
            )
        )

        logger.info(f"otel initialized for service: {config.service_name}")
        return tracer_provider, meter_provider

    except Exception as e:
        logger.error(f"failed to initialize otel: {e}")
        return None, None


def shutdown_otel() -> None:
    """Shutdown OpenTelemetry providers."""

    logger = get_logger(__name__)
    try:
        tracer_provider = trace.get_tracer_provider()
        if hasattr(tracer_provider, "shutdown"):
            tracer_provider.shutdown()

        meter_provider = metrics.get_meter_provider()
        if hasattr(meter_provider, "shutdown"):
            meter_provider.shutdown()

        logger.info("otel shutdown completed")

    except Exception as e:
        logger.error(f"error during otel shutdown: {e}")
