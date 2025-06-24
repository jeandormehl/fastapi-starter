import re
from ipaddress import AddressValueError, IPv4Address, IPv6Address

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.paths import ROOT_PATH


# noinspection PyNestedDecorators
class APIConfiguration(BaseSettings):
    """API configuration."""

    _HOSTNAME_PATTERN = re.compile(r'^(?!-)[A-Za-z0-9-]{1,63}(?<!-)$')

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=ROOT_PATH / '.env',
        env_file_encoding='utf-8',
        env_prefix='API_',
        extra='ignore',
    )

    cors_origins: list[str] = Field(
        default=['*'], description='Allowed CORS origins for API requests'
    )
    allowed_hosts: list[str] = Field(
        default=['*'], description='Allowed host headers for API requests'
    )
    host: str = Field(
        default='127.0.0.1', description='API server bind address (IP or hostname)'
    )
    port: int = Field(
        default=8080, ge=1, le=65535, description='API server port number'
    )

    @field_validator('host')
    @classmethod
    def validate_host(cls, value: str) -> str:
        return cls._validate_single_host(value)

    @field_validator('allowed_hosts', 'cors_origins', mode='before')
    @classmethod
    def validate_host_lists(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            value = [value]

        validated_hosts = []
        for host in value:
            if host == '*':
                validated_hosts.append(host)
            else:
                validated_hosts.append(cls._validate_single_host(host))

        return validated_hosts

    @classmethod
    def _validate_single_host(cls, host: str) -> str:
        try:
            IPv4Address(host)
            return host
        except AddressValueError:
            pass

        try:
            IPv6Address(host)
            return host
        except AddressValueError:
            pass

        return cls._validate_hostname(host)

    @classmethod
    def _validate_hostname(cls, hostname: str) -> str:
        if not hostname or len(hostname) > 253:
            msg = f'invalid hostname length: {hostname}'
            raise ValueError(msg)

        labels = hostname.split('.')
        invalid_labels = [
            label for label in labels if not cls._HOSTNAME_PATTERN.match(label)
        ]

        if invalid_labels:
            msg = f'invalid hostname "{hostname}": invalid labels {invalid_labels}'
            raise ValueError(msg)

        return hostname
