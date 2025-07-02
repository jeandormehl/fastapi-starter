from functools import lru_cache
from typing import Literal
from zoneinfo import available_timezones

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app import __version__
from app.core.paths import ROOT_PATH

from .configs import APIConfiguration, DatabaseConfiguration, LogConfiguration


# noinspection PyNestedDecorators,PyArgumentList
class Configuration(BaseSettings):
    """Application configuration."""

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=ROOT_PATH / '.env',
        env_file_encoding='utf-8',
        extra='ignore',
    )

    app_name: str = Field('FastAPI Starter', description='Application name')
    app_description: str = Field(
        'FastAPI starter for rapid development', description='Application description'
    )
    app_version: str = __version__
    app_secret_key: SecretStr = Field(
        ..., description='Application secret key', min_length=16, repr=False
    )
    app_environment: Literal['test', 'local', 'dev', 'qa', 'prod'] = Field(
        'local', description='Application environment', validation_alias='ENVIRONMENT'
    )
    app_timezone: str = Field(
        'UTC', description='Application timezone', validation_alias='TZ'
    )

    admin_client_id: str = Field(..., description='Admin client ID')
    admin_password: SecretStr = Field(
        ..., description='Administrator password', repr=False
    )

    api: APIConfiguration = APIConfiguration()
    database: DatabaseConfiguration = DatabaseConfiguration()
    log: LogConfiguration = LogConfiguration()

    @property
    def app_debug(self) -> bool:
        return self.app_environment in ['test', 'local', 'dev']

    @field_validator('app_timezone')
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        if v not in available_timezones():
            msg = f'not a valid timezone: {v}'
            raise ValueError(msg)
        return v


# noinspection PyArgumentList
@lru_cache
def get_config() -> Configuration:
    """
    Get cached application settings.
    """
    return Configuration()
