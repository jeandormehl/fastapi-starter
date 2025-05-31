from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

from prisma.models import Client, Scope

from app.services.jwt_service import JWTPayload


def create_test_client(
    client_id: str = "test-client",
    scopes: list[str] | None = None,
    is_active: bool = True,
    **kwargs,
) -> Client:
    """Create a test client with specified attributes."""

    if scopes is None:
        scopes = ["read", "write"]

    scope_objects = [
        Scope(id=f"test-scope-{scope}", name=scope, description=f"{scope} access")
        for scope in scopes
    ]

    return Client(
        id=kwargs.get("id", f"{client_id}-id"),
        client_id=client_id,
        hashed_secret="$2b$12$Brj6p08XnWd1IZotcue9GubHhOxUuaG8KGvRgSyWHI5fGJL8JiBM.",
        is_active=is_active,
        scopes=scope_objects,
        created_at=kwargs.get("created_at", datetime.now(timezone.utc)),
        updated_at=kwargs.get("updated_at", datetime.now(timezone.utc)),
    )


def create_jwt_payload(
    client_id: str = "test-client", scopes: list[str] | None = None, **kwargs
) -> JWTPayload:
    """Create a test JWT payload."""

    if scopes is None:
        scopes = ["read", "write"]

    now = datetime.now(timezone.utc)

    return JWTPayload(
        id=kwargs.get("id", f"{client_id}-id"),
        client_id=client_id,
        exp=kwargs.get("exp", int(now.timestamp()) + 3600),  # 1 hour from now
        iat=kwargs.get("iat", int(now.timestamp())),
        scopes=scopes,
    )


def create_mock_database() -> Mock:
    """Create a comprehensive mock database."""

    mock_db = Mock()
    mock_db.client = AsyncMock()
    mock_db.scope = AsyncMock()
    mock_db.connect = AsyncMock()
    mock_db.disconnect = AsyncMock()

    # Setup common return values
    mock_db.client.find_unique = AsyncMock()
    mock_db.client.find_many = AsyncMock(return_value=[])
    mock_db.client.create = AsyncMock()
    mock_db.client.update = AsyncMock()
    mock_db.client.delete = AsyncMock()

    return mock_db


async def run_async_test(coro):
    """Run an async test function."""

    return await coro


def assert_log_contains(mock_logger, level: str, message_fragment: str):
    """Assert that logger was called with specific level and message fragment."""

    method = getattr(mock_logger, level)
    method.assert_called()

    # Check if any call contains the message fragment
    for call in method.call_args_list:
        args, kwargs = call
        if args and message_fragment in str(args[0]):
            return
        if "message" in kwargs and message_fragment in str(kwargs["message"]):
            return

    msg = (
        f"Expected {level} log containing '{message_fragment}' not found. "
        f"Actual calls: {method.call_args_list}"
    )
    raise AssertionError(msg)


def assert_exception_details(
    exception, expected_code=None, expected_message_fragment=None
):
    """Assert exception details match expectations."""
    if expected_code:
        assert exception.error_code == expected_code

    if expected_message_fragment:
        assert expected_message_fragment in str(exception)
