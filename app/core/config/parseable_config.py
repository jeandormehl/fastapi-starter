from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.common.constants import ROOT_PATH


class ParseableConfiguration(BaseSettings):
    """Parseable logging configuration."""

    model_config = SettingsConfigDict(
        env_file=f"{ROOT_PATH}/.env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="PARSEABLE_",
    )

    enabled: bool = Field(False, description="Enable Parseable logging")
    url: str = Field("http://localhost:8000", description="Parseable URL")
    username: str = Field("admin", description="Parseable username")
    password: SecretStr = Field("password", description="Parseable password")
    batch_size: int = Field(100, description="Parseable batch size")
    flush_interval: float = Field(5.0, description="Parseable flush interval")
    max_retries: int = Field(3, description="Parseable max retries")
    retry_delay: float = Field(1.0, description="Parseable retry delay")

    api_stream: str = Field("app-logs", description="API request stream")
    task_stream: str = Field("task-logs", description="Task execution stream")
    error_stream: str = Field("error-logs", description="Error stream")
    metrics_stream: str = Field("metrics-logs", description="Metrics stream")

    @property
    def auth_header(self) -> str:
        """Get the Basic Auth header value."""
        import base64

        credentials = f"{self.username}:{self.password.get_secret_value()}"
        encoded = base64.b64encode(credentials.encode()).decode()

        return f"Basic {encoded}"
