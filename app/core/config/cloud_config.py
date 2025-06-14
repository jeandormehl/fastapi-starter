from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.common.constants import ROOT_PATH


class CloudConfiguration(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=f"{ROOT_PATH}/.env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="CLOUD_",
    )

    provider: str | None = Field(None, description="Cloud provider: aws, azure, gcp")

    # noinspection PyNestedDecorators
    @field_validator("cloud_provider", mode="after")
    @classmethod
    def validate_cloud_provider(cls, value: str | None) -> str | None:
        if not value:
            return None
        valid_providers = ["aws", "azure", "gcp"]
        if value.lower() not in valid_providers:
            msg = f"cloud provider must be one of {valid_providers}"
            raise ValueError(msg)
        return value.lower()
