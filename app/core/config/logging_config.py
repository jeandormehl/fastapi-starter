from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.common.constants import ROOT_PATH


class LoggingConfiguration(BaseSettings):
    """Logging configuration."""

    model_config = SettingsConfigDict(
        env_file=f"{ROOT_PATH}/.env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="LOG_",
    )

    level: str = Field("INFO", description="Log level")
    to_file: bool = Field(True, description="Enable file logging")
    file_path: str = Field("/app/static/logs", description="Log file path")
    enable_json: bool = Field(False, description="Enable json logging")

    # noinspection PyNestedDecorators
    @field_validator("level", mode="after")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        valid_levels = [
            "TRACE",
            "DEBUG",
            "INFO",
            "SUCCESS",
            "WARNING",
            "ERROR",
            "CRITICAL",
        ]
        if value.upper() not in valid_levels:
            msg = f"log level must be one of {valid_levels}"
            raise ValueError(msg)
        return value.upper()
