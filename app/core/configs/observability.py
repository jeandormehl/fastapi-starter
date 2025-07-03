from pydantic import AnyUrl, BaseModel, Field
from pydantic_settings import SettingsConfigDict

from app.core.paths import ROOT_PATH


class ObservabilityConfiguration(BaseModel):
    """Observability pillars (traces, metrics, logs) configuration."""

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=ROOT_PATH / '.env',
        env_file_encoding='utf-8',
        env_prefix='OBS_',
        extra='ignore',
    )

    enabled: bool = Field(
        True, description='Enable/disable all observability features.'
    )

    traces_endpoint: AnyUrl = Field(
        AnyUrl('http://tempo:4317'),
        description='OTLP gRPC endpoint used by trace exporter.',
    )
    tracing_sample_ratio: float = Field(
        1.0,
        ge=0.0,
        le=1.0,
        description='Sampling ratio (1.0 = 100 % of requests traced).',
    )

    excluded_urls: str = Field('', description='Excluded urls list.')
