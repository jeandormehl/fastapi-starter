from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.common.constants import ROOT_PATH


class ApiConfiguration(BaseSettings):
    """API configuration."""

    model_config = SettingsConfigDict(
        env_file=f"{ROOT_PATH}/.env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="API_",
    )

    cors_origins: list[str] = Field(["*"], description="API CORS origins")
    allowed_hosts: list[str] = Field(["*"], description="API allowed hosts")
    host: str = Field("127.0.0.1", description="API host")
    port: int = Field(8080, description="API port")
