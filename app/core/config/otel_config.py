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
    service_version: str = Field("0.0.0", description="Service version")
    service_namespace: str = Field("app-metrics", description="Service namespace")
    service_env: str = Field("dev", description="Deployment environment")

    # OTLP Exporter Settings
    exporter_otlp_endpoint: str = Field(
        "http://otel-collector:4317", description="OTLP gRPC endpoint"
    )
    exporter_otlp_headers: SecretStr | None = Field(
        None, description="OTLP headers (e.g., authorization)"
    )
    exporter_otlp_timeout: int = Field(30, description="OTLP timeout in seconds")
    exporter_otlp_compression: str = Field("gzip", description="OTLP compression")

    # Tracing Settings
    traces_enabled: bool = Field(True, description="Enable tracing")
    traces_sample_rate: float = Field(
        1.0, ge=0.0, le=1.0, description="Trace sample rate"
    )

    # Metrics Settings
    metrics_enabled: bool = Field(True, description="Enable metrics")
    metrics_export_interval: int = Field(
        60, description="Metrics export interval in seconds"
    )

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

    enable_cloud_detection: bool = False
    max_queue_size: int = 2048
    schedule_delay_millis: int = 5000
    max_export_batch_size: int = 512
    export_timeout_millis: int = 30000
