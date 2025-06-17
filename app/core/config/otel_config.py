from opentelemetry.sdk.resources import (
    SERVICE_NAME,
    SERVICE_NAMESPACE,
    SERVICE_VERSION,
)
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.common.constants import ROOT_PATH


class OtelConfiguration(BaseSettings):
    """OpenTelemetry configuration with validation."""

    model_config = SettingsConfigDict(
        env_file=f"{ROOT_PATH}/.env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="OTEL_",
    )

    # General OTEL Settings
    enabled: bool = Field(True, description="Enable OpenTelemetry instrumentation")
    service_name: str = Field("fastapi-starter", description="Service name for traces")
    service_version: str = Field("1.0.0", description="Service version")
    service_namespace: str = Field("fastapi-app", description="Service namespace")
    service_env: str = Field("local", description="Deployment environment")

    exporter_otlp_endpoint: str = Field(
        "http://otel-collector:4317", description="OTLP gRPC endpoint"
    )
    exporter_otlp_headers: SecretStr | None = Field(
        None, description="OTLP headers (e.g., authorization)"
    )
    exporter_otlp_timeout: int = Field(10, description="OTLP timeout in seconds")
    exporter_otlp_compression: str = Field("gzip", description="OTLP compression")

    traces_enabled: bool = Field(True, description="Enable tracing")
    traces_sample_rate: float = Field(
        1.0, ge=0.0, le=1.0, description="Trace sample rate (1.0 = 100%)"
    )

    logs_enabled: bool = Field(True, description="Enable OTEL logs export")
    logs_export_endpoint: str = Field(
        "http://otel-collector:4317", description="OTLP logs endpoint"
    )

    # Metrics Settings
    metrics_enabled: bool = Field(True, description="Enable metrics")
    metrics_export_interval: int = Field(
        30,
        description="Metrics export interval in seconds",
    )

    @property
    def resource_attributes(self) -> dict[str, str]:
        return {
            SERVICE_NAME: self.service_name,
            SERVICE_VERSION: self.service_version,
            SERVICE_NAMESPACE: self.service_env,
        }

    # Instrumentation Settings
    instrument_fastapi: bool = Field(True, description="Enable FastAPI instrumentation")
    instrument_redis: bool = Field(True, description="Enable Redis instrumentation")
    instrument_requests: bool = Field(
        True, description="Enable HTTP requests instrumentation"
    )
    instrument_logging: bool = Field(True, description="Enable logging instrumentation")

    # Custom Settings
    capture_request_body: bool = Field(
        False, description="Capture request body in spans"
    )
    capture_response_body: bool = Field(
        False, description="Capture response body in spans"
    )
    db_statement_sanitization: bool = Field(True, description="Sanitize DB statements")

    # Resource Detection
    detect_resource: bool = Field(
        True, description="Enable automatic resource detection"
    )

    enable_cloud_detection: bool = Field(False, description="Enable cloud detection")
    max_queue_size: int = Field(2048, description="Max queue size")
    schedule_delay_millis: int = Field(1000, description="Schedule delay in ms")
    max_export_batch_size: int = Field(512, description="Max export batch size")
    export_timeout_millis: int = Field(10000, description="Export timeout in ms")
