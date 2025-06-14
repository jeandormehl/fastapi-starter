from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.common.constants import ROOT_PATH


class JWTConfiguration(BaseSettings):
    """JWT configuration."""

    model_config = SettingsConfigDict(
        env_file=f"{ROOT_PATH}/.env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="JWT_",
    )

    algorithm: str = Field("HS256", description="JWT algorithm")
    access_token_expire_minutes: int = Field(
        60, description="JWT access token expiry minutes"
    )
