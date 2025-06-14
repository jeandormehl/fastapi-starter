from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.common.constants import ROOT_PATH


class DatabaseConfiguration(BaseSettings):
    """Database configuration."""

    model_config = SettingsConfigDict(
        env_file=f"{ROOT_PATH}/.env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="DATABASE_",
    )

    url: SecretStr = Field(..., description="Database connection string")
