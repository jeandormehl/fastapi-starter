import os
from typing import Any

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
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import (
    ALWAYS_OFF,
    ALWAYS_ON,
    TraceIdRatioBased,
)

from app.common.logging import get_logger
from app.core.config import Configuration
from app.core.config.otel_config import OtelConfiguration


def create_resource(config: OtelConfiguration) -> Resource:
    """Create OpenTelemetry resource with service information."""

    base_attributes = {
        SERVICE_NAME: config.service_name,
        SERVICE_VERSION: config.service_version,
        SERVICE_NAMESPACE: config.service_env,
        DEPLOYMENT_ENVIRONMENT: config.service_env,
    }

    # Add additional attributes safely
    try:
        import platform
        import socket

        base_attributes.update(
            {
                "host.name": socket.gethostname(),
                "os.type": platform.system().lower(),
                "process.pid": os.getpid(),
            }
        )

        # Container detection
        try:
            with open("/proc/self/cgroup") as f:
                cgroup_content = f.read()
                if "docker" in cgroup_content:
                    for line in cgroup_content.split("\n"):
                        if "docker" in line and "/" in line:
                            container_id = line.split("/")[-1][:12]
                            if container_id:
                                base_attributes["container.id"] = container_id
                            break

        except (FileNotFoundError, PermissionError):
            pass

    except Exception as e:
        get_logger(__name__).debug(
            f"failed to detect additional resource attributes: {e}"
        )

    return Resource.create(base_attributes)


def setup_tracing(
    config: OtelConfiguration, resource: Resource
) -> TracerProvider | None:
    """Setup OpenTelemetry tracing with improved error handling."""

    if not config.traces_enabled:
        return None

    try:
        # Create sampler based on sample rate
        if config.traces_sample_rate >= 1.0:
            sampler = ALWAYS_ON

        elif config.traces_sample_rate <= 0.0:
            sampler = ALWAYS_OFF

        else:
            sampler = TraceIdRatioBased(config.traces_sample_rate)

        # Create tracer provider
        tracer_provider = TracerProvider(resource=resource, sampler=sampler)

        # Create OTLP exporter
        exporter_kwargs = {
            "endpoint": config.exporter_otlp_endpoint,
            "timeout": config.exporter_otlp_timeout,
        }

        _add_otlp_headers(config, exporter_kwargs)

        otlp_exporter = OTLPSpanExporter(**exporter_kwargs)

        # Add span processor
        span_processor = BatchSpanProcessor(
            otlp_exporter,
            max_queue_size=config.max_queue_size,
            schedule_delay_millis=config.schedule_delay_millis,
            max_export_batch_size=config.max_export_batch_size,
            export_timeout_millis=config.export_timeout_millis,
        )
        tracer_provider.add_span_processor(span_processor)

        # Set global tracer provider
        trace.set_tracer_provider(tracer_provider)
        get_logger(__name__).info("otel tracing initialized successfully")

        return tracer_provider

    except Exception as e:
        get_logger(__name__).error(f"failed to setup tracing: {e}")
        return None


def setup_metrics(
    config: OtelConfiguration, resource: Resource
) -> MeterProvider | None:
    """Setup OpenTelemetry metrics with improved error handling."""

    if not config.metrics_enabled:
        return None

    try:
        # Create OTLP metric exporter
        exporter_kwargs = {
            "endpoint": config.exporter_otlp_endpoint,
            "timeout": config.exporter_otlp_timeout,
        }

        _add_otlp_headers(config, exporter_kwargs)

        otlp_exporter = OTLPMetricExporter(**exporter_kwargs)

        # Create metric reader
        metric_reader = PeriodicExportingMetricReader(
            exporter=otlp_exporter,
            export_interval_millis=config.metrics_export_interval * 1000,
        )

        # Create meter provider
        meter_provider = MeterProvider(
            resource=resource, metric_readers=[metric_reader]
        )

        # Set global meter provider
        metrics.set_meter_provider(meter_provider)
        get_logger(__name__).info("otel metrics initialized successfully")

        return meter_provider

    except Exception as e:
        get_logger(__name__).error(f"failed to setup metrics: {e}")
        return None


def initialize_otel() -> tuple[TracerProvider | None, MeterProvider | None]:
    """Initialize OpenTelemetry with comprehensive error handling."""
    config = di[Configuration].otel
    logger = get_logger(__name__)

    if not config.enabled:
        logger.info("otel disabled by configuration")
        return None, None

    try:
        # Create resource
        resource = create_resource(config)
        logger.info(f"created resource with attributes: {dict(resource.attributes)}")

        # Setup tracing and metrics
        tracer_provider = setup_tracing(config, resource)
        meter_provider = setup_metrics(config, resource)

        # Configure propagators
        try:
            from opentelemetry.propagate import set_global_textmap
            from opentelemetry.propagators.b3 import B3MultiFormat
            from opentelemetry.propagators.composite import CompositePropagator
            from opentelemetry.propagators.jaeger import JaegerPropagator
            from opentelemetry.trace.propagation.tracecontext import (
                TraceContextTextMapPropagator,
            )

            set_global_textmap(
                CompositePropagator(
                    [
                        TraceContextTextMapPropagator(),
                        B3MultiFormat(),
                        JaegerPropagator(),
                    ]
                )
            )
            logger.info("context propagation configured successfully")

        except Exception as e:
            logger.warning(f"failed to configure context propagation: {e}")

        logger.info(f"otel initialized successfully for service: {config.service_name}")
        return tracer_provider, meter_provider

    except Exception as e:
        logger.error(f"failed to initialize OpenTelemetry: {e}")
        return None, None


def shutdown_otel() -> None:
    """Shutdown OpenTelemetry providers with proper error handling."""
    logger = get_logger(__name__)

    try:
        # Shutdown tracer provider
        tracer_provider = trace.get_tracer_provider()
        if hasattr(tracer_provider, "shutdown"):
            tracer_provider.shutdown()
            logger.info("tracer provider shutdown completed")

        # Shutdown meter provider
        meter_provider = metrics.get_meter_provider()
        if hasattr(meter_provider, "shutdown"):
            meter_provider.shutdown()
            logger.info("meter provider shutdown completed")

        logger.info("otel shutdown completed")

    except Exception as e:
        logger.error(f"error during OTEL shutdown: {e}")


def _add_otlp_headers(
    config: OtelConfiguration, exporter_kwargs: dict[str, Any]
) -> None:
    # Add headers if configured
    if config.exporter_otlp_headers:
        try:
            headers_str = config.exporter_otlp_headers.get_secret_value()
            if headers_str:
                headers = {}
                for header in headers_str.split(","):
                    if "=" in header:
                        key, value = header.split("=", 1)
                        headers[key.strip()] = value.strip()
                exporter_kwargs["headers"] = headers

        except Exception as e:
            get_logger(__name__).warning(f"failed to parse otlp headers: {e}")
