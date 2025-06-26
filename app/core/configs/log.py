from typing import Literal

from pydantic import AnyUrl, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.paths import ROOT_PATH


class LogConfiguration(BaseSettings):
    """Logging configuration with Loguru and Loki support."""

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=ROOT_PATH / '.env',
        env_file_encoding='utf-8',
        env_prefix='LOG_',
        extra='ignore',
    )

    level: Literal[
        'TRACE', 'DEBUG', 'INFO', 'SUCCESS', 'WARNING', 'ERROR', 'CRITICAL'
    ] = Field('INFO', description='Minimum log level')

    to_file: bool = Field(False, description='Enable file logging')
    file_path: str = Field('app/static/app.log', description='Log file path')

    to_loki: bool = Field(False, description='Enable Loki logging integration')
    loki_url: AnyUrl = Field(
        AnyUrl('http://loki:3100/loki/api/v1/push'),
        description='Loki push endpoint URL',
        repr=False,
    )
    loki_username: str | None = Field(None, description='Loki basic auth username')
    loki_password: SecretStr | None = Field(
        None, description='Loki basic auth password', repr=False
    )

    @model_validator(mode='after')
    def validate_logging_paths_and_urls(self) -> 'LogConfiguration':
        if self.to_file and not self.file_path:
            msg = 'file_path must be provided if to_file is true'
            raise ValueError(msg)

        if self.to_loki and not self.loki_url:
            msg = 'loki_url must be provided if to_loki is true'
            raise ValueError(msg)

        return self
