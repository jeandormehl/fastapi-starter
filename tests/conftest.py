from datetime import datetime
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo

import pytest
from fastapi.requests import Request
from kink import di
from prisma.models import Client, Scope
from pytest_mock import MockerFixture

from app.core.config import Configuration
from app.core.constants import TESTS_PATH
from app.core.logging import initialize_logging
from app.domain.v1.auth.services import JWTService
from app.infrastructure.database import Database


@pytest.fixture(scope="session")
def test_config() -> Configuration:
    """Test configuration with safe defaults."""

    return Configuration(
        _env_file=f"{TESTS_PATH}/.env.test",
        admin_password="test-admin-password-very-secure",
        app_environment="test",
        app_secret_key="test-secret-key-very-long-and-secure-for-testing",
        app_timezone="Africa/Harare",
        log_enable_json="False",
        log_file_path=f"{TESTS_PATH}/logs/test.log",
        log_level="DEBUG",
        log_to_file="True",
        parseable_enabled="False",
        jwt_algorithm="HS256",
        jwt_access_token_expire_minutes=30,
    )


@pytest.fixture(autouse=True)
def setup_logging(test_config):
    """Fixture to initialize logging for each test function."""

    initialize_logging(test_config)


@pytest.fixture(scope="session")
def test_timezone():
    """Provide test timezone for consistent time handling."""

    return ZoneInfo("Africa/Harare")


@pytest.fixture
def mock_database():
    """Create a mock database instance."""

    mock_db = Mock(spec=Database)
    mock_db.client = AsyncMock()
    mock_db.scope = AsyncMock()
    mock_db.connect = AsyncMock()
    mock_db.disconnect = AsyncMock()

    return mock_db


@pytest.fixture
def jwt_service(test_config):
    """Create JWT service instance for testing."""

    return JWTService(test_config)


@pytest.fixture(autouse=True)
def setup_di_container(test_config, test_timezone, mock_database, jwt_service):
    """Setup dependency injection container for each test."""

    # Clear any existing container state
    di.clear_cache()

    # Register test dependencies
    di[Configuration] = test_config
    di["timezone"] = test_timezone

    di[Database] = mock_database

    di[JWTService] = jwt_service

    yield di

    # Cleanup after test
    di.clear_cache()


@pytest.fixture
def test_client_model(test_timezone):
    """Create a test client model."""

    return Client(
        id="test-client-123",
        client_id="test-client-id",
        hashed_secret="test-secret",
        name="Test Client",
        is_active=True,
        scopes=[
            Scope(id="test-scope-121", name="read", description="Read access"),
            Scope(id="test-scope-122", name="write", description="Write access"),
            Scope(id="test-scope-123", name="admin", description="Admin access"),
        ],
        created_at=datetime.now(test_timezone),
        updated_at=datetime.now(test_timezone),
    )


@pytest.fixture
def test_client_inactive(test_timezone):
    """Create an inactive test client model."""

    return Client(
        id="inactive-client-123",
        client_id="inactive-client-id",
        hashed_secret="inactive-secret",
        name="Inactive Test Client",
        is_active=False,
        scopes=[],
        created_at=datetime.now(test_timezone),
        updated_at=datetime.now(test_timezone),
    )


@pytest.fixture
def test_jwt_token(jwt_service, test_client_model):
    """Create a valid test JWT token."""

    return jwt_service.create_access_token(
        _id=test_client_model.id,
        client_id=test_client_model.client_id,
        scopes=["read", "write"],
    )


@pytest.fixture
def test_admin_jwt_token(jwt_service, test_client_model):
    """Create a valid admin JWT token."""

    return jwt_service.create_access_token(
        _id=test_client_model.id,
        client_id=test_client_model.client_id,
        scopes=["read", "write", "admin"],
    )


@pytest.fixture
def expired_jwt_token(jwt_service, test_client_model, test_timezone):
    """Create an expired JWT token for testing."""
    from datetime import datetime, timedelta

    import jwt

    expired_payload = {
        "id": test_client_model.id,
        "client_id": test_client_model.client_id,
        "exp": int((datetime.now(test_timezone) - timedelta(hours=1)).timestamp()),
        "iat": int((datetime.now(test_timezone) - timedelta(hours=2)).timestamp()),
        "scopes": ["read"],
    }

    return jwt.encode(
        expired_payload, jwt_service.secret_key, algorithm=jwt_service.algorithm
    )


# noinspection HttpUrlsUsage
@pytest.fixture
def mock_request(mocker: MockerFixture):
    """Create a comprehensive mock request object."""
    mock_req = mocker.MagicMock(spec=Request)

    # URL and path information
    mock_req.url.path = "/test/path"
    mock_req.base_url = "http://test.example.com"
    mock_req.query_params = {}
    mock_req.path_params = {}

    # Client information
    mock_req.client = mocker.MagicMock()
    mock_req.client.host = "127.0.0.1"

    # Request state with trace information
    mock_req.state = Mock()
    mock_req.state.trace_id = "test-trace-id-12345"
    mock_req.state.request_id = "test-request-id-67890"

    # Headers
    mock_req.headers = {
        "user-agent": "pytest-test-agent/1.0",
        "referer": "http://test.example.com/previous",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/json",
        "authorization": "Bearer test-token",
    }

    return mock_req
