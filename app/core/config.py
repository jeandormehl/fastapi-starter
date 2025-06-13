from zoneinfo import available_timezones

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app import __version__
from app.common.constants import ROOT_PATH


# noinspection PyNestedDecorators
class Configuration(BaseSettings):
    """Application Settings."""

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

    admin_password: SecretStr = Field(..., description="Administrator password")

    api_cors_origins: list[str] = Field(["*"], description="API CORS origins")
    api_allowed_hosts: list[str] = Field(["*"], description="API allowed hosts")
    api_host: str = Field("127.0.0.1", description="API host")
    api_port: int = Field(8080, description="API port")

    cloud_provider: str | None = Field(
        None, description="Cloud provider: aws, azure, gcp"
    )

    database_url: SecretStr = Field(None, description="Database connection string")

    log_level: str = Field("INFO", description="Log level")
    log_to_file: bool = Field(True, description="Enable file logging")
    log_file_path: str = Field("/app/static/logs", description="Log file path")
    log_enable_json: bool = Field(False, description="Enable json logging")

    parseable_enabled: bool = Field(False, description="Enable Parseable logging")
    parseable_url: str = Field("http://localhost:8000", description="Parseable URL")
    parseable_username: str = Field("admin", description="Parseable stream")
    parseable_password: SecretStr = Field("password", description="Parseable password")
    parseable_batch_size: int = Field(100, description="Parseable batch size")
    parseable_flush_interval: float = Field(5.0, description="Parseable flush interval")
    parseable_max_retries: int = Field(3, description="Parseable max retries")
    parseable_retry_delay: float = Field(1.0, description="Parseable retry delay")

    parseable_api_stream: str = Field("app-logs", description="API request stream")
    parseable_task_stream: str = Field("task-logs", description="Task execution stream")
    parseable_error_stream: str = Field("error-logs", description="Error stream")
    parseable_metrics_stream: str = Field("metrics-logs", description="Metrics stream")

    jwt_algorithm: str = Field("HS256", description="JWT algorithm")
    jwt_access_token_expire_minutes: int = Field(
        60, description="JWT access token expiry minutes"
    )

    # Request logging settings
    request_logging_enabled: bool = Field(
        True, description="Enable request/response logging to database"
    )
    request_logging_log_headers: bool = Field(
        False, description="Log request/response headers"
    )
    request_logging_excluded_paths: list[str] = Field(
        default_factory=lambda: [
            "/health",
            "/metrics",
            "/static",
            "/docs",
            "/redoc",
            "/openapi.json",
        ],
        description="Paths to exclude from request logging",
    )
    request_logging_excluded_methods: list[str] = Field(
        default_factory=lambda: ["OPTIONS", "HEAD"],
        description="HTTP methods to exclude from request logging",
    )
    request_logging_retention_days: int = Field(
        30, description="Days to retain request logs before cleanup"
    )
    request_logging_cleanup_interval_hours: int = Field(
        6, description="Hours between cleanup task runs"
    )
    request_logging_max_body_size: int = Field(
        default=100000,
        description="Maximum size of request/response bodies to log",
    )

    task_logging_enabled: bool = Field(
        True, description="Enable task execution logging to database"
    )
    task_logging_retention_days: int = Field(
        30, description="Days to retain task logs before cleanup"
    )
    task_logging_excluded_tasks: list[str] = Field(
        default_factory=lambda: [],
        description="Task names to exclude from logging",
    )
    task_logging_cleanup_interval_hours: int = Field(
        6, description="Hours between cleanup task runs"
    )

    # Idempotency settings
    idempotency_enabled: bool = Field(
        True, description="Enable idempotency checks for requests and tasks"
    )
    idempotency_request_enabled: bool = Field(
        True, description="Enable idempotency for API requests"
    )
    idempotency_task_enabled: bool = Field(
        True, description="Enable idempotency for background tasks"
    )
    idempotency_cache_ttl_hours: int = Field(
        24, description="Hours to cache idempotency results"
    )
    idempotency_cleanup_interval_hours: int = Field(
        6, description="Hours between idempotency cache cleanup"
    )
    idempotency_header_names: list[str] = Field(
        default_factory=lambda: ["idempotency-key", "x-idempotency-key", "request-id"],
        description="Header names to check for idempotency keys",
    )
    idempotency_supported_methods: list[str] = Field(
        default_factory=lambda: ["POST", "PUT", "PATCH"],
        description="HTTP methods that support idempotency",
    )
    idempotency_excluded_paths: list[str] = Field(
        default_factory=lambda: [
            "/v1/health",
            "/v1/metrics",
            "/v1/docs",
            "/v1/redoc",
            "/v1/docs/openapi.json",
        ],
        description="Paths to exclude from idempotency checks",
    )
    idempotency_max_key_length: int = Field(
        255, description="Maximum length of idempotency keys"
    )
    idempotency_content_verification: bool = Field(
        True, description="Verify request content matches on idempotency key reuse"
    )

    @property
    def app_debug(self) -> bool:
        return self.app_environment in ["test", "local", "sandbox"]

    @property
    def parseable_auth_header(self) -> str:
        """Get the Basic Auth header value."""
        import base64

        credentials = (
            f"{self.parseable_username}:{self.parseable_password.get_secret_value()}"
        )
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    # app_timezone validator
    @field_validator("app_timezone", mode="after")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        if value not in available_timezones():
            msg = f"not a valid timezone: {value}"
            raise ValueError(msg)
        return value

    # app_environment validator
    @field_validator("app_environment", mode="after")
    @classmethod
    def validate_environment(cls, value: str) -> str:
        valid_envs = ["test", "local", "sandbox", "qa", "prod"]
        if value.lower() not in valid_envs:
            msg = f"Environment must be one of {valid_envs}"
            raise ValueError(msg)
        return value.lower()

    # cloud_provider validator
    @field_validator("cloud_provider", mode="after")
    @classmethod
    def validate_cloud_provider(cls, value: str | None) -> str | None:
        if not value:
            return None
        valid_providers = ["aws", "azure", "gcp"]
        if value.lower() not in valid_providers:
            msg = f"Cloud provider must be one of {valid_providers}"
            raise ValueError(msg)
        return value.lower()

    # log_level validator
    @field_validator("log_level", mode="after")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        valid_levels = [
            "TRACE",
            "DEBUG",
            "INFO",
            "SUCCESS",
            "WARNING",
            "ERROR",
            "CRITICAL",
        ]
        if value.upper() not in valid_levels:
            msg = f"Log level must be one of {valid_levels}"
            raise ValueError(msg)
        return value.upper()

    @field_validator("request_logging_retention_days")
    @classmethod
    def validate_request_retention_days(cls, v: int) -> int:
        if v < 1:
            msg = "retention_days must be at least 1"
            raise ValueError(msg)
        if v > 365:
            msg = "retention_days cannot exceed 365"
            raise ValueError(msg)
        return v

    @field_validator("task_logging_retention_days")
    @classmethod
    def validate_task_retention_days(cls, v: int) -> int:
        if v < 1:
            msg = "retention_days must be at least 1"
            raise ValueError(msg)
        if v > 365:
            msg = "retention_days cannot exceed 365"
            raise ValueError(msg)
        return v

    @field_validator("idempotency_cache_ttl_hours")
    @classmethod
    def validate_cache_ttl(cls, v: int) -> int:
        if v < 1 or v > 168:  # 1 hour to 1 week
            msg = "cache TTL must be between 1 and 168 hours"
            raise ValueError(msg)
        return v

    @field_validator("idempotency_max_key_length")
    @classmethod
    def validate_max_key_length(cls, v: int) -> int:
        if v < 1 or v > 500:
            msg = "max key length must be between 1 and 500"
            raise ValueError(msg)
        return v
