import logging
import sys
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from kink import Container, di
from prisma.models import Client, Scope
from pydiator_core.mediatr import pydiator
from pydiator_core.mediatr_container import MediatrContainer
from pytest_mock import MockerFixture
from taskiq import AsyncBroker, InMemoryBroker

# Import application components
from app.common.constants import TESTS_PATH
from app.core.application import get_application
from app.core.config import Configuration
from app.domain.v1.auth.schemas import JWTPayload
from app.domain.v1.auth.services import JWTService
from app.domain.v1.health.services import HealthService
from app.domain.v1.idempotency.services.idempotency_service import IdempotencyService
from app.domain.v1.request_handler_map import RequestHandlerMap
from app.infrastructure.database import Database
from app.infrastructure.taskiq.config import TaskiqConfiguration
from app.infrastructure.taskiq.task_manager import TaskManager

# Disable all logging during tests
logging.disable(logging.CRITICAL)

# Suppress asyncio, httpx, and other noisy loggers
for logger_name in ["asyncio", "httpx", "uvicorn", "fastapi", "sqlalchemy", "taskiq"]:
    logging.getLogger(logger_name).disabled = True

# Mock loguru to prevent any logging output during tests
sys.modules["loguru"].logger = Mock()


def pytest_configure(config):
    """Configure pytest with custom markers and settings."""
    markers = [
        "unit: Unit tests for individual components",
        "integration: Integration tests for component interactions",
        "slow: Tests that take longer than 1 second",
        "database: Tests requiring database interactions",
        "auth: Authentication and authorization tests",
        "tasks: Taskiq background task tests",
        "api: API endpoint tests",
    ]

    for marker in markers:
        config.addinivalue_line("markers", marker)


@pytest.fixture(scope="session", autouse=True)
def suppress_logging():
    """Completely suppress all logging during test execution."""
    # Disable standard logging
    logging.disable(logging.CRITICAL)

    # Mock loguru logger to prevent any output
    with patch("app.common.logging.logger.logger") as mock_logger:
        mock_logger.add = Mock()
        mock_logger.remove = Mock()
        mock_logger.bind = Mock(return_value=mock_logger)
        mock_logger.debug = Mock()
        mock_logger.info = Mock()
        mock_logger.warning = Mock()
        mock_logger.error = Mock()
        mock_logger.critical = Mock()

        yield mock_logger


@pytest.fixture
def test_config() -> Configuration:
    """Centralized test configuration with optimized settings."""

    # Ensure test environment file exists
    test_env_path = Path(TESTS_PATH) / ".env.test"
    if not test_env_path.exists():
        test_env_path.parent.mkdir(parents=True, exist_ok=True)
        test_env_path.write_text(
            """
APP_NAME="Test FastAPI Starter"
APP_DESCRIPTION="Test API for FastAPI Starter"
APP_ENVIRONMENT="test"
APP_SECRET_KEY="test-secret-key-very-long-and-secure-for-comprehensive-testing"
APP_TIMEZONE="UTC"
DATABASE_URL="sqlite:///:memory:"
LOG_TO_FILE="False"
LOG_LEVEL="CRITICAL"
LOG_ENABLE_JSON="False"
PARSEABLE_ENABLED="False"
REQUEST_LOGGING_ENABLED="False"
        """.strip()
        )

    return Configuration(
        _env_file=str(test_env_path),
        app_name="Test FastAPI Starter",
        app_description="Test API for FastAPI Starter",
        app_environment="test",
        app_secret_key="test-secret-key-very-long-and-secure-for-comprehensive-testing",
        app_timezone="UTC",
        database_url="sqlite:///:memory:",
        log_to_file=False,
        log_level="CRITICAL",
        log_enable_json=False,
        parseable_enabled=False,
        request_logging_enabled=False,
        jwt_algorithm="HS256",
        jwt_access_token_expire_minutes=30,
        admin_password="test-admin-password-very-secure-for-testing",
    )


@pytest.fixture(scope="session")
def test_timezone() -> ZoneInfo:
    """Provide consistent timezone for all tests."""
    return ZoneInfo("UTC")


@pytest.fixture
def mock_database() -> Mock:
    """Comprehensive mock database with all required methods."""
    mock_db = Mock(spec=Database)

    # Setup client operations
    mock_db.client = AsyncMock()
    mock_db.client.find_unique = AsyncMock()
    mock_db.client.find_many = AsyncMock(return_value=[])
    mock_db.client.create = AsyncMock()
    mock_db.client.update = AsyncMock()
    mock_db.client.delete = AsyncMock()
    mock_db.client.count = AsyncMock(return_value=0)

    # Setup scope operations
    mock_db.scope = AsyncMock()
    mock_db.scope.find_unique = AsyncMock()
    mock_db.scope.find_many = AsyncMock(return_value=[])
    mock_db.scope.create = AsyncMock()

    # Connection management
    mock_db.connect = AsyncMock()
    mock_db.disconnect = AsyncMock()
    mock_db.is_connected = Mock(return_value=True)

    return mock_db


@pytest.fixture
def jwt_service(test_config: Configuration) -> JWTService:
    """JWT service instance for testing."""
    return JWTService(test_config)


@pytest.fixture
def taskiq_config() -> TaskiqConfiguration:
    """Taskiq configuration optimized for testing."""
    return TaskiqConfiguration(
        broker_type="memory",
        queue="test_queue",
        default_retry_count=0,  # No retries in tests
        default_retry_delay=1,
        task_timeout=5,  # Short timeout for tests
        result_ttl=60,
        enable_metrics=False,  # Disable metrics in tests
        sanitize_logs=True,
    )


@pytest.fixture
def mock_broker(taskiq_config: TaskiqConfiguration) -> AsyncBroker:  # noqa: ARG001
    """Mock async broker for task testing."""
    broker = InMemoryBroker()
    broker.result_backend = Mock()
    broker.result_backend.get_result = AsyncMock()
    return broker


@pytest.fixture
def task_manager(mock_broker: AsyncBroker, suppress_logging) -> TaskManager:
    """Task manager instance for testing."""
    # Mock logging initialization to prevent any logging setup
    with patch("app.common.logging.initialize_logging") as mock_init:
        mock_init.return_value = None

        # Mock logger manager to prevent logging
        with patch("app.common.logging.logger._logger_manager") as mock_manager:
            mock_manager.get_logger = Mock(return_value=suppress_logging)

            return TaskManager(mock_broker)


@pytest.fixture
def health_service(test_config) -> TaskManager:
    return HealthService(test_config)


@pytest.fixture(autouse=True)
def setup_di_container(
    test_config: Configuration,
    test_timezone: ZoneInfo,
    mock_database: Mock,
    jwt_service: JWTService,
    mock_broker: AsyncBroker,
    task_manager: TaskManager,
    health_service: HealthService,
    suppress_logging,
) -> Generator[Container]:
    """Setup dependency injection container for each test."""

    def _setup_mediatr():
        mediatr = MediatrContainer()

        for config in RequestHandlerMap:
            request_type, handler_cls = config.value

            # Register handler in DI container as factory
            di.factories[handler_cls] = lambda _, handler=handler_cls: handler()
            mediatr.register_request(request_type, di[handler_cls])

        pydiator.ready(container=mediatr)

    # Clear existing container state
    di.clear_cache()

    # Register core dependencies
    di[Configuration] = test_config
    di["timezone"] = test_timezone
    di[Database] = mock_database
    di[JWTService] = jwt_service
    di[AsyncBroker] = mock_broker
    di[TaskManager] = task_manager
    di[HealthService] = health_service
    di[IdempotencyService] = Mock(spec=IdempotencyService)

    # Mock logging initialization to prevent any logging setup
    with patch("app.common.logging.initialize_logging") as mock_init:
        mock_init.return_value = None

        # Mock logger manager to prevent logging
        with patch("app.common.logging.logger._logger_manager") as mock_manager:
            mock_manager.get_logger = Mock(return_value=suppress_logging)

            _setup_mediatr()
            yield di

    # Cleanup after test
    di.clear_cache()


@pytest.fixture
def app(test_config, setup_di_container: Container) -> FastAPI:  # noqa: ARG001
    """FastAPI application instance for testing."""

    # Mock all logging components to prevent setup
    with (
        patch("app.common.logging.initialize_logging"),
        patch("app.common.logging.logger.LoggerManager"),
        patch("app.common.logging.parseable_sink.ParseableSink"),
    ):
        return get_application(test_config)


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Synchronous test client for API testing."""
    return TestClient(app)


@pytest.fixture
async def async_client(app: FastAPI) -> AsyncGenerator[AsyncClient]:
    """Asynchronous test client for advanced API testing."""
    async with AsyncClient(
        base_url="http://localhost:8080",
        transport=ASGITransport(app=app),
        follow_redirects=True,
    ) as client:
        yield client


# noinspection HttpUrlsUsage,PyTestUnpassedFixture
@pytest.fixture
def mock_request(mocker: MockerFixture):
    """Comprehensive mock request object for middleware testing."""
    mock_req = mocker.MagicMock()

    # URL and path information
    mock_req.url.path = "/api/test"
    mock_req.method = "GET"
    mock_req.base_url = "http://test.example.com"
    mock_req.query_params = {}
    mock_req.path_params = {}

    # Client information
    mock_req.client.host = "127.0.0.1"
    mock_req.client.port = 0

    # Request state with tracing
    mock_req.state.trace_id = "test-trace-12345"
    mock_req.state.request_id = "test-request-67890"

    # Headers
    mock_req.headers = {
        "user-agent": "pytest-test-agent/1.0",
        "content-type": "application/json",
        "accept": "application/json",
    }

    return mock_req


# Test data factories
@pytest.fixture
def test_client_active(test_timezone: ZoneInfo) -> Client:
    """Create active test client model."""
    return Client(
        id="test-client-active-123",
        client_id="active-test-client",
        hashed_secret="$2b$12$Brj6p08XnWd1IZotcue9GubHhOxUuaG8KGvRgSyWHI5fGJL8JiBM.",
        name="Active Test Client",
        is_active=True,
        scopes=[
            Scope(id="scope-read", name="read", description="Read access"),
            Scope(id="scope-write", name="write", description="Write access"),
            Scope(id="scope-admin", name="admin", description="Admin access"),
        ],
        created_at=datetime.now(test_timezone),
        updated_at=datetime.now(test_timezone),
    )


@pytest.fixture
def test_client_inactive(test_timezone: ZoneInfo) -> Client:
    """Create inactive test client model."""
    return Client(
        id="test-client-inactive-456",
        client_id="inactive-test-client",
        hashed_secret="$2b$12$Brj6p08XnWd1IZotcue9GubHhOxUuaG8KGvRgSyWHI5fGJL8JiBM.",
        name="Inactive Test Client",
        is_active=False,
        scopes=[],
        created_at=datetime.now(test_timezone),
        updated_at=datetime.now(test_timezone),
    )


@pytest.fixture
def test_jwt_payload() -> JWTPayload:
    """Create test JWT payload."""
    now = datetime.now(UTC)
    return JWTPayload(
        id="test-client-active-123",
        client_id="active-test-client",
        exp=int(now.timestamp()) + 3600,
        iat=int(now.timestamp()),
        scopes=["read", "write", "admin"],
    )


@pytest.fixture
def test_scopes() -> list[Scope]:
    """Create test scope models."""
    return [
        Scope(id="scope-read", name="read", description="Read access"),
        Scope(id="scope-write", name="write", description="Write access"),
        Scope(id="scope-admin", name="admin", description="Admin access"),
    ]
