from zoneinfo import available_timezones

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app import __version__
from app.common.constants import ROOT_PATH

from .api_config import ApiConfiguration
from .cloud_config import CloudConfiguration
from .database_config import DatabaseConfiguration
from .idempotency_config import IdempotencyConfiguration
from .jwt_config import JWTConfiguration
from .logging_config import LoggingConfiguration
from .otel_config import OtelConfiguration
from .parseable_config import ParseableConfiguration
from .request_logging_config import RequestLoggingConfiguration
from .task_logging_config import TaskLoggingConfiguration
from .taskiq_config import TaskiqConfiguration


# noinspection PyNestedDecorators
class Configuration(BaseSettings):
    """Application Settings with nested configuration support."""

    model_config = SettingsConfigDict(
        env_file=f"{ROOT_PATH}/.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field("FastAPI Starter", description="Application name")
    app_description: str = Field(
        "FastAPI starter for rapid development", description="Application description"
    )
    app_version: str = __version__
    app_environment: str = Field(
        "local", description="Environment: test, local, sandbox, qa, prod"
    )
    app_secret_key: SecretStr = Field(
        ..., description="Application secret key", min_length=16
    )
    app_timezone: str = Field("UTC", description="Application timezone")

    admin_client_id: str = Field(..., description="Admin client ID")
    admin_password: SecretStr = Field(..., description="Administrator password")

    api: ApiConfiguration = ApiConfiguration()
    cloud: CloudConfiguration = CloudConfiguration()
    database: DatabaseConfiguration = DatabaseConfiguration()
    idempotency: IdempotencyConfiguration = IdempotencyConfiguration()
    jwt: JWTConfiguration = JWTConfiguration()
    logging: LoggingConfiguration = LoggingConfiguration()
    parseable: ParseableConfiguration = ParseableConfiguration()
    request_logging: RequestLoggingConfiguration = RequestLoggingConfiguration()
    task_logging: TaskLoggingConfiguration = TaskLoggingConfiguration()
    taskiq: TaskiqConfiguration = TaskiqConfiguration()

    @property
    def otel(self) -> OtelConfiguration:
        return OtelConfiguration(
            service_name=self.app_name,
            service_version=self.app_version,
            service_env=self.app_environment,
        )

    @property
    def app_debug(self) -> bool:
        return self.app_environment in ["test", "local", "sandbox"]

    # Validators
    @field_validator("app_timezone", mode="after")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        if value not in available_timezones():
            msg = f"not a valid timezone: {value}"
            raise ValueError(msg)
        return value

    @field_validator("app_environment", mode="after")
    @classmethod
    def validate_environment(cls, value: str) -> str:
        valid_envs = ["test", "local", "sandbox", "qa", "prod"]
        if value.lower() not in valid_envs:
            msg = f"environment must be one of {valid_envs}"
            raise ValueError(msg)
        return value.lower()
