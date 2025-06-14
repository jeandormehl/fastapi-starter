from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.common.constants import ROOT_PATH


class RequestLoggingConfiguration(BaseSettings):
    """Request logging configuration."""

    model_config = SettingsConfigDict(
        env_file=f"{ROOT_PATH}/.env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="REQUEST_LOGGING_",
    )

    enabled: bool = Field(
        True, description="Enable request/response logging to database"
    )
    log_headers: bool = Field(False, description="Log request/response headers")
    excluded_paths: list[str] = Field(
        default_factory=lambda: [
            "/v1/health",
            "/v1/metrics",
            "/v1/static",
            "/v1/docs",
            "/v1/redoc",
            "/v1/docs/openapi.json",
        ],
        description="Paths to exclude from request logging",
    )
    excluded_methods: list[str] = Field(
        default_factory=lambda: ["OPTIONS", "HEAD"],
        description="HTTP methods to exclude from request logging",
    )
    retention_days: int = Field(
        30, description="Days to retain request logs before cleanup"
    )
    cleanup_interval_hours: int = Field(
        6, description="Hours between cleanup task runs"
    )
    max_body_size: int = Field(
        default=100000,
        description="Maximum size of request/response bodies to log",
    )

    # noinspection PyNestedDecorators
    @field_validator("retention_days", mode="after")
    @classmethod
    def validate_retention_days(cls, v: int) -> int:
        if v < 1:
            msg = "retention_days must be at least 1"
            raise ValueError(msg)
        if v > 365:
            msg = "retention_days cannot exceed 365"
            raise ValueError(msg)
        return v
