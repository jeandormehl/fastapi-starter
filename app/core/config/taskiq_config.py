from pydantic import Field, SecretStr, field_validator
from pydantic_core.core_schema import ValidationInfo
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.common.constants import ROOT_PATH
from app.infrastructure.taskiq.schemas import BrokerType


class TaskiqConfiguration(BaseSettings):
    """Taskiq configuration with validation."""

    model_config = SettingsConfigDict(
        env_file=f"{ROOT_PATH}/.env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="TASKIQ_",
    )

    # Broker Configuration
    broker_type: BrokerType = Field(BrokerType.MEMORY, description="Broker type")
    broker_url: SecretStr | None = Field(None, description="Broker connection URL")
    result_backend_url: SecretStr | None = Field(None, description="Result backend URL")

    # Queue Configuration
    queue: str = Field("default", description="Default queue name")

    # Connection Management
    retry_on_timeout: bool = Field(True, description="Retry on timeout")

    # Task Execution
    default_retry_count: int = Field(3, ge=0, le=10, description="Default retry count")
    default_retry_delay: int = Field(
        60, ge=1, description="Default retry delay in seconds"
    )
    max_retry_delay: int = Field(
        3600, ge=1, description="Maximum retry delay in seconds"
    )
    task_timeout: int = Field(300, ge=1, description="Task timeout in seconds")

    # Result Storage
    result_ttl: int = Field(3600, ge=60, description="Result TTL in seconds")
    keep_failed_results: bool = Field(True, description="Keep failed task results")

    # Metrics
    enable_metrics: bool = Field(True, description="Enable metrics collection")
    metrics_retention_days: int = Field(
        7, ge=1, description="Metrics retention in days"
    )

    # Security
    enable_task_encryption: bool = Field(
        False, description="Enable task payload encryption"
    )
    encryption_key: SecretStr | None = Field(None, description="Encryption key")
    sanitize_logs: bool = Field(True, description="Sanitize sensitive data in logs")

    # noinspection PyNestedDecorators
    @field_validator("broker_url", mode="after")
    @classmethod
    def validate_broker_url(cls, value: SecretStr, values: ValidationInfo) -> SecretStr:
        """Validate broker URL is provided for non-memory brokers."""

        if values.data.get("broker_type") != BrokerType.MEMORY and value is None:
            msg = f"broker_url is required for {values.data.get('broker_type')} broker"
            raise ValueError(msg)
        return value

    # noinspection PyNestedDecorators
    @field_validator("encryption_key", mode="after")
    @classmethod
    def validate_encryption_key(
        cls, value: SecretStr | None, values: ValidationInfo
    ) -> SecretStr | None:
        if values.data.get("enable_task_encryption") and not value:
            msg = "encryption_key is required when task encryption is enabled"
            raise ValueError(msg)
        return value
