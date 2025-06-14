from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.common.constants import ROOT_PATH


# noinspection PyNestedDecorators
class IdempotencyConfiguration(BaseSettings):
    """Idempotency configuration."""

    model_config = SettingsConfigDict(
        env_file=f"{ROOT_PATH}/.env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="IDEMPOTENCY_",
    )

    enabled: bool = Field(
        True, description="Enable idempotency checks for requests and tasks"
    )
    request_enabled: bool = Field(
        True, description="Enable idempotency for API requests"
    )
    task_enabled: bool = Field(
        True, description="Enable idempotency for background tasks"
    )
    cache_ttl_hours: int = Field(24, description="Hours to cache idempotency results")
    cleanup_interval_hours: int = Field(
        6, description="Hours between idempotency cache cleanup"
    )
    header_names: list[str] = Field(
        default_factory=lambda: ["x-idempotency-key"],
        description="Header names to check for idempotency keys",
    )
    supported_methods: list[str] = Field(
        default_factory=lambda: ["POST", "PUT", "PATCH"],
        description="HTTP methods that support idempotency",
    )
    excluded_paths: list[str] = Field(
        default_factory=lambda: [
            "/v1/health",
            "/v1/metrics",
            "/v1/docs",
            "/v1/redoc",
            "/v1/docs/openapi.json",
        ],
        description="Paths to exclude from idempotency checks",
    )
    max_key_length: int = Field(255, description="Maximum length of idempotency keys")
    content_verification: bool = Field(
        True, description="Verify request content matches on idempotency key reuse"
    )

    @field_validator("cache_ttl_hours")
    @classmethod
    def validate_cache_ttl(cls, v: int) -> int:
        if v < 1 or v > 168:  # 1 hour to 1 week
            msg = "cache TTL must be between 1 and 168 hours"
            raise ValueError(msg)
        return v

    @field_validator("max_key_length")
    @classmethod
    def validate_max_key_length(cls, v: int) -> int:
        if v < 1 or v > 500:
            msg = "max key length must be between 1 and 500"
            raise ValueError(msg)
        return v

    @field_validator("cleanup_interval_hours")
    @classmethod
    def validate_cleanup_interval(cls, v: int) -> int:
        if v < 1 or v > 24:
            msg = "cleanup interval must be between 1 and 24 hours"
            raise ValueError(msg)
        return v

    @field_validator("header_names")
    @classmethod
    def validate_header_names(cls, v: list[str]) -> list[str]:
        if not v:
            msg = "at least one idempotency header name must be specified"
            raise ValueError(msg)
        return [name.lower() for name in v]
