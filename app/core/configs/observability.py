from pydantic import AnyUrl, BaseModel, Field
from pydantic_settings import SettingsConfigDict

from app.core.paths import ROOT_PATH


class ObservabilityConfiguration(BaseModel):
    """Observability pillars (traces, metrics, logs) configuration."""

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=ROOT_PATH / '.env',
        env_file_encoding='utf-8',
        env_prefix='OBSERVABILITY_',
        extra='ignore',
    )

    enabled: bool = Field(True, description='Enable observability features')
    traces_endpoint: AnyUrl = Field(
        AnyUrl('http://tempo:4317'),
        description='OTLP gRPC endpoint used by trace exporter.',
    )
    tracing_sample_ratio: float = Field(
        1.0, description='Tracing sample ratio (0.0 to 1.0)'
    )
    traces_to_console: bool = Field(False, description='Output traces to console')
    excluded_urls: str = Field(
        '/health,/metrics,/docs,/openapi.json',
        description='Comma-separated list of excluded URLs.',
    )
