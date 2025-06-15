import contextlib
import logging
import os

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
    ResourceDetector,
    get_aggregated_resources,
)
from opentelemetry.sdk.trace import TracerProvider, sampling
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.common.logging import get_logger
from app.core.config import Configuration
from app.core.config.otel_config import OtelConfiguration


class DefaultResourceDetector(ResourceDetector):
    """Basic resource detector for common attributes."""

    def detect(self) -> Resource:
        """Detect basic resource attributes."""

        try:
            import platform
            import socket

            attributes = {
                "host.name": socket.gethostname(),
                "os.type": platform.system().lower(),
                "process.pid": os.getpid(),
                "process.executable.name": os.path.basename(os.path.basename(__file__)),
            }

            try:
                with open("/proc/self/cgroup") as f:
                    cgroup_content = f.read()
                    if "docker" in cgroup_content:
                        # Extract container ID from cgroup
                        for line in cgroup_content.split("\n"):
                            if "docker" in line and "/" in line:
                                container_id = line.split("/")[-1][:12]
                                if container_id:
                                    attributes["container.id"] = container_id
                                break
            except (FileNotFoundError, PermissionError, Exception):
                contextlib.suppress(FileNotFoundError, PermissionError, Exception)

            return Resource.create(attributes)

        except Exception as e:
            logging.warning(f"failed to detect default resources: {e}")
            return Resource.create({})


# noinspection PyUnresolvedReferences
def create_resource(config: OtelConfiguration) -> Resource:
    """Create OpenTelemetry resource with service information and detection."""

    # Base resource attributes from configuration
    base_attributes = {
        SERVICE_NAME: config.service_name,
        SERVICE_VERSION: config.service_version,
        SERVICE_NAMESPACE: config.service_namespace,
        DEPLOYMENT_ENVIRONMENT: config.service_namespace,
    }

    base_resource = Resource.create(base_attributes)

    if not config.detect_resource:
        return base_resource

    try:
        # Collect resource detectors with error handling
        detectors = []

        # Add environment detector (always safe)
        try:
            from opentelemetry.sdk.resources import OTELResourceDetector

            detectors.append(OTELResourceDetector())
        except ImportError:
            contextlib.suppress(ImportError)

        # Add process detector
        try:
            from opentelemetry.sdk.resources import ProcessResourceDetector

            detectors.append(ProcessResourceDetector())
        except ImportError:
            contextlib.suppress(ImportError)

        # Add OS detector
        try:
            from opentelemetry.sdk.resources import OSResourceDetector

            detectors.append(OSResourceDetector())
        except ImportError:
            contextlib.suppress(ImportError)

        # Add our default detector
        detectors.append(DefaultResourceDetector())

        # Add cloud-specific detectors if available (with timeout)
        if hasattr(config, "enable_cloud_detection") and config.enable_cloud_detection:
            try:
                # AWS EC2 detector with timeout protection
                from opentelemetry.sdk.extension.aws.resource.ec2 import (
                    AwsEc2ResourceDetector,
                )

                detectors.append(AwsEc2ResourceDetector(timeout=2))  # 2 second timeout

            except ImportError:
                contextlib.suppress(ImportError)

            except Exception as e:
                get_logger(__name__).debug(f"aws ec2 detector failed: {e}")

            try:
                # GCP detector
                from opentelemetry.sdk.extension.gcp.resource import GcpResourceDetector

                detectors.append(GcpResourceDetector(timeout=2))

            except ImportError:
                contextlib.suppress(ImportError)

            except Exception as e:
                get_logger(__name__).debug(f"gcp detector failed: {e}")

        if detectors:
            # Use get_aggregated_resources with proper detectors and timeout
            return get_aggregated_resources(
                detectors,
                base_resource,
                timeout=5,  # 5 second total timeout for all detectors
            )

        return base_resource

    except Exception as e:
        get_logger(__name__).warning(f"resource detection failed: {e}")
        return base_resource


# noinspection DuplicatedCode
def setup_tracing(
    config: OtelConfiguration, resource: Resource
) -> TracerProvider | None:
    """Setup OpenTelemetry tracing with improved error handling."""

    if not config.traces_enabled:
        return None

    try:
        # Create sampler based on sample rate
        if config.traces_sample_rate == 1.0:
            sampler = sampling.ALWAYS_ON

        elif config.traces_sample_rate == 0.0:
            sampler = sampling.ALWAYS_OFF

        else:
            sampler = sampling.TraceIdRatioBased(config.traces_sample_rate)

        # Create tracer provider
        tracer_provider = TracerProvider(resource=resource, sampler=sampler)

        # Create OTLP exporter with better error handling
        exporter_kwargs = {
            "endpoint": config.exporter_otlp_endpoint,
            "timeout": config.exporter_otlp_timeout,
            # TODO: This fails: gzip literal?
            # "compression": getattr(config, "exporter_otlp_compression", None),
        }

        if hasattr(config, "exporter_otlp_headers") and config.exporter_otlp_headers:
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

        otlp_exporter = OTLPSpanExporter(**exporter_kwargs)

        # Add span processor with batching configuration
        span_processor = BatchSpanProcessor(
            otlp_exporter,
            max_queue_size=getattr(config, "max_queue_size", 2048),
            schedule_delay_millis=getattr(config, "schedule_delay_millis", 5000),
            max_export_batch_size=getattr(config, "max_export_batch_size", 512),
            export_timeout_millis=getattr(config, "export_timeout_millis", 30000),
        )
        tracer_provider.add_span_processor(span_processor)

        # Set global tracer provider
        trace.set_tracer_provider(tracer_provider)
        get_logger(__name__).info("otel tracing initialized successfully")

        return tracer_provider

    except Exception as e:
        get_logger(__name__).error(f"failed to setup tracing: {e}")

        return None


# noinspection DuplicatedCode
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

        if hasattr(config, "exporter_otlp_headers") and config.exporter_otlp_headers:
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
                get_logger(__name__).warning(
                    f"failed to parse otlp headers for metrics: {e}"
                )

        otlp_exporter = OTLPMetricExporter(**exporter_kwargs)

        # Create metric reader
        metric_reader = PeriodicExportingMetricReader(
            exporter=otlp_exporter,
            export_interval_millis=getattr(config, "metrics_export_interval", 60)
            * 1000,
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
        get_logger(__name__).error(f"Failed to setup metrics: {e}")

        return None


def initialize_otel() -> tuple[TracerProvider | None, MeterProvider | None]:
    """Initialize OpenTelemetry with comprehensive error handling."""

    config = di[Configuration].otel
    logger = get_logger(__name__)

    if not config.enabled:
        logger.info("otel disabled by configuration")

        return None, None

    try:
        # Create resource with better error handling
        resource = create_resource(config)
        logger.info(f"created resource with attributes: {dict(resource.attributes)}")

        # Setup tracing and metrics
        tracer_provider = setup_tracing(config, resource)
        meter_provider = setup_metrics(config, resource)

        # Set up context propagation for FastAPI middleware
        try:
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
        logger.error(f"failed to initialize otel: {e}")
        return None, None


def shutdown_otel() -> None:
    """Shutdown OpenTelemetry providers with proper error handling."""

    logger = get_logger(__name__)
    try:
        # Shutdown tracer provider
        tracer_provider = trace.get_tracer_provider()
        if hasattr(tracer_provider, "shutdown"):
            try:
                tracer_provider.shutdown()
                logger.info("tracer provider shutdown completed")

            except Exception as e:
                logger.error(f"error shutting down tracer provider: {e}")

        # Shutdown meter provider
        meter_provider = metrics.get_meter_provider()
        if hasattr(meter_provider, "shutdown"):
            try:
                meter_provider.shutdown()
                logger.info("meter provider shutdown completed")
            except Exception as e:
                logger.error(f"error shutting down meter provider: {e}")

        logger.info("otel shutdown completed")

    except Exception as e:
        logger.error(f"error during otel shutdown: {e}")
