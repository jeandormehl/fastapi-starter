import re

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.paths import ROOT_PATH


# noinspection PyNestedDecorators
class DatabaseConfiguration(BaseSettings):
    """Database configuration."""

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=ROOT_PATH / '.env',
        env_file_encoding='utf-8',
        env_prefix='DATABASE_',
        extra='ignore',
    )

    url: SecretStr = Field(..., description='The full database connection', repr=False)
    timeout: float = Field(
        5.0,
        description=(
            'The maximum time (in seconds) the database client will wait '
            'for a connection to be established'
        ),
        ge=0,
    )

    @field_validator('url')
    @classmethod
    def validate_db_url_format(cls, v: SecretStr) -> SecretStr:
        """Validates the database URL to ensure it uses a recognized scheme and has a
        basic structural integrity for Prisma-supported databases.
        """
        url_str = v.get_secret_value()
        supported_schemes = {
            'postgresql',
            'postgres',
            'mysql',
            'sqlite',
            'sqlserver',
            'mongodb',
            'cockroachdb',
        }

        scheme_match = re.match(r'^([a-zA-Z0-9_]+)://', url_str)
        if not scheme_match:
            msg = (
                f"invalid database url format: '{url_str}'. "
                'the url must start with a recognized scheme followed by '
                "'://' (e.g., 'postgresql://')."
            )
            raise ValueError(msg)

        extracted_scheme = scheme_match.group(1).lower()
        if extracted_scheme not in supported_schemes:
            msg = (
                f"Unsupported database scheme: '{extracted_scheme}'. "
                f'Prisma currently supports: {", ".join(sorted(supported_schemes))}.'
            )
            raise ValueError(msg)

        if extracted_scheme in {
            'postgresql',
            'postgres',
            'mysql',
            'sqlserver',
            'mongodb',
            'cockroachdb',
        }:
            if len(url_str) <= len(extracted_scheme) + 3:
                msg = (
                    f"incomplete '{extracted_scheme}' database url. "
                    'expected host, port, and/or database name after the scheme '
                    "(e.g., 'postgresql://host:port/dbname')."
                )
                raise ValueError(msg)

        elif extracted_scheme == 'sqlite' and not url_str.startswith('sqlite:///'):
            msg = (
                f"invalid sqlite url format: '{url_str}'. "
                'for file-based sqlite, please use '
                "'sqlite:///path/to/your/database.db'."
            )
            raise ValueError(msg)
        return v
