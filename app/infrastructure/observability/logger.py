import logging

# noinspection PyProtectedMember
from opentelemetry._logs import set_logger_provider

# noinspection PyProtectedMember
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter

# noinspection PyProtectedMember
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler

# noinspection PyProtectedMember
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource

from app.common.logging import get_logger
from app.core.config.otel_config import OtelConfiguration


class OtelLoggingHandler:
    """OpenTelemetry logging integration handler."""

    def __init__(self, config: OtelConfiguration, resource: Resource) -> None:
        self.config = config
        self.resource = resource
        self.logger = get_logger(__name__)
        self._setup_otel_logging()

    def _setup_otel_logging(self) -> None:
        """Setup OpenTelemetry logging integration."""

        if not self.config.logs_enabled:
            return

        try:
            exporter_kwargs = {
                "endpoint": self.config.logs_export_endpoint,
                "timeout": self.config.exporter_otlp_timeout,
            }

            if self.config.exporter_otlp_headers:
                headers_str = self.config.exporter_otlp_headers.get_secret_value()
                if headers_str:
                    headers = {}
                    for header in headers_str.split(","):
                        if "=" in header:
                            key, value = header.split("=", 1)
                            headers[key.strip()] = value.strip()
                    exporter_kwargs["headers"] = headers

            log_exporter = OTLPLogExporter(**exporter_kwargs)

            # Create logger provider
            logger_provider = LoggerProvider(resource=self.resource)
            set_logger_provider(logger_provider)

            # Add log processor
            logger_provider.add_log_record_processor(
                BatchLogRecordProcessor(log_exporter)
            )

            # Create OTEL logging handler
            handler = LoggingHandler(
                level=logging.INFO, logger_provider=logger_provider
            )

            # Add handler to root logger
            logging.getLogger().addHandler(handler)

            self.logger.info("otel logging integration initialized successfully")

        except Exception as e:
            self.logger.error(f"failed to setup otel logging: {e}")
