from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.common.constants import ROOT_PATH


class TaskLoggingConfiguration(BaseSettings):
    """Task logging configuration."""

    model_config = SettingsConfigDict(
        env_file=f"{ROOT_PATH}/.env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="TASK_LOGGING_",
    )

    enabled: bool = Field(True, description="Enable task execution logging to database")
    retention_days: int = Field(
        30, description="Days to retain task logs before cleanup"
    )
    excluded_tasks: list[str] = Field(
        default_factory=lambda: [],
        description="Task names to exclude from logging",
    )
    cleanup_interval_hours: int = Field(
        6, description="Hours between cleanup task runs"
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
