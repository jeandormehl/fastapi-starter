import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, Mock

from httpx import AsyncClient, Response
from prisma.models import Client, Scope

from app.domain.v1.auth.schemas import JWTPayload


class TestDataFactory:
    """Factory for creating consistent test data."""

    @staticmethod
    def create_client(
        client_id: str = "test-client",
        scopes: list[str] | None = None,
        is_active: bool = True,
        **overrides,
    ) -> Client:
        """Create test client with specified attributes."""
        if scopes is None:
            scopes = ["read", "write"]

        scope_objects = [
            Scope(
                id=f"scope-{scope}-{i}",
                name=scope,
                description=f"{scope.title()} access scope",
            )
            for i, scope in enumerate(scopes)
        ]

        defaults = {
            "id": f"{client_id}-id",
            "client_id": client_id,
            "hashed_secret": (
                "$2b$12$Brj6p08XnWd1IZotcue9GubHhOxUuaG8KGvRgSyWHI5fGJL8JiBM."
            ),
            "is_active": is_active,
            "scopes": scope_objects,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }

        defaults.update(overrides)
        return Client(**defaults)

    @staticmethod
    def create_jwt_payload(
        client_id: str = "test-client", scopes: list[str] | None = None, **overrides
    ) -> JWTPayload:
        """Create test JWT payload."""
        if scopes is None:
            scopes = ["read", "write"]

        now = datetime.now(UTC)
        defaults = {
            "id": f"{client_id}-id",
            "client_id": client_id,
            "exp": int(now.timestamp()) + 3600,
            "iat": int(now.timestamp()),
            "scopes": scopes,
            "type": "access_token",
        }

        defaults.update(overrides)
        return JWTPayload(**defaults)

    @staticmethod
    def create_scope(name: str, description: str | None = None) -> Scope:
        """Create test scope."""
        return Scope(
            id=f"scope-{name}-{datetime.now(UTC).timestamp()}",
            name=name,
            description=description or f"{name.title()} access scope",
        )


class DatabaseMockHelper:
    """Helper for setting up database mock responses."""

    @staticmethod
    def setup_client_find_unique(
        mock_db: Mock, client: Client | None = None, client_id: str | None = None
    ) -> None:
        """Setup mock database client find_unique response."""
        if client_id and not client:
            client = TestDataFactory.create_client(client_id=client_id)

        mock_db.client.find_unique.return_value = client

    @staticmethod
    def setup_client_find_many(mock_db: Mock, clients: list[Client]) -> None:
        """Setup mock database client find_many response."""
        mock_db.client.find_many.return_value = clients

    @staticmethod
    def setup_scope_find_many(mock_db: Mock, scopes: list[Scope]) -> None:
        """Setup mock database scope find_many response."""
        mock_db.scope.find_many.return_value = scopes


class APITestHelper:
    """Helper for API testing operations."""

    @staticmethod
    async def assert_response_status(
        response: Response, expected_status: int, message: str | None = None
    ) -> None:
        """Assert response has expected status code."""
        actual_status = response.status_code
        if actual_status != expected_status:
            error_msg = (
                f"Expected status {expected_status}, got {actual_status}. "
                f"Response: {response.text}"
            )
            if message:
                error_msg = f"{message}. {error_msg}"
            raise AssertionError(error_msg)

    @staticmethod
    async def assert_response_json(
        response: Response,
        expected_keys: list[str] | None = None,
        expected_values: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Assert response JSON structure and values."""
        try:
            json_data = response.json()
        except Exception as e:
            msg = f"Response is not valid JSON: {e}"
            raise AssertionError(msg)

        if expected_keys:
            missing_keys = set(expected_keys) - set(json_data.keys())
            if missing_keys:
                msg = f"Missing keys in response: {missing_keys}"
                raise AssertionError(msg)

        if expected_values:
            for key, expected_value in expected_values.items():
                if key not in json_data:
                    msg = f"Key '{key}' not found in response"
                    raise AssertionError(msg)
                if json_data[key] != expected_value:
                    msg = (
                        f"Key '{key}': expected {expected_value}, got {json_data[key]}"
                    )
                    raise AssertionError(msg)

        return json_data

    @staticmethod
    async def make_authenticated_request(
        client: AsyncClient, method: str, url: str, token: str, **kwargs
    ) -> Response:
        """Make authenticated API request."""
        headers = kwargs.get("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        kwargs["headers"] = headers

        return await client.request(method, url, **kwargs)


class AsyncTestRunner:
    """Helper for running async tests and operations."""

    @staticmethod
    async def run_with_timeout(coro, timeout: float = 5.0):  # noqa: ASYNC109
        """Run coroutine with timeout."""
        return await asyncio.wait_for(coro, timeout=timeout)

    @staticmethod
    def run_sync(coro):
        """Run async coroutine synchronously."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


class MockHelper:
    """Helper for creating and configuring mocks."""

    @staticmethod
    def create_async_mock_with_return(return_value: Any) -> AsyncMock:
        """Create AsyncMock with specific return value."""
        mock = AsyncMock()
        mock.return_value = return_value
        return mock

    @staticmethod
    def setup_mock_call_tracking(mock: Mock) -> Callable[[], list[Any]]:
        """Setup call tracking for mock and return tracker function."""
        calls = []

        def track_calls(*args, **kwargs):
            calls.append((args, kwargs))
            return mock.return_value

        mock.side_effect = track_calls
        return lambda: calls.copy()

    @staticmethod
    def assert_mock_called_with_subset(
        mock: Mock, expected_subset: dict[str, Any], call_index: int = 0
    ) -> None:
        """Assert mock was called with arguments containing expected subset."""
        if not mock.call_args_list:
            msg = "Mock was not called"
            raise AssertionError(msg)

        if call_index >= len(mock.call_args_list):
            msg = f"Mock was not called {call_index + 1} times"
            raise AssertionError(msg)

        call_args, call_kwargs = mock.call_args_list[call_index]

        for key, expected_value in expected_subset.items():
            if key not in call_kwargs:
                msg = f"Expected key '{key}' not found in call kwargs"
                raise AssertionError(msg)
            if call_kwargs[key] != expected_value:
                msg = f"Key '{key}': expected {expected_value}, got {call_kwargs[key]}"
                raise AssertionError(msg)


# Test assertion helpers
def assert_no_logging_calls(mock_logger: Mock) -> None:
    """Assert that no logging calls were made."""
    log_methods = ["debug", "info", "warning", "error", "critical"]
    for method_name in log_methods:
        method = getattr(mock_logger, method_name, None)
        if method and method.called:
            msg = f"Unexpected {method_name} log call: {method.call_args_list}"
            raise AssertionError(msg)


def assert_exception_details(
    exception: Exception,
    expected_type: type,
    expected_message_fragment: str | None = None,
    expected_code: str | None = None,
) -> None:
    """Assert exception details match expectations."""
    if not isinstance(exception, expected_type):
        msg = (
            f"Expected exception type {expected_type.__name__}, "
            f"got {type(exception).__name__}"
        )
        raise AssertionError(msg)

    if expected_message_fragment and expected_message_fragment not in str(exception):
        msg = (
            f"Expected message fragment '{expected_message_fragment}' "
            f"not found in: {exception!s}"
        )
        raise AssertionError(msg)

    # noinspection PyUnresolvedReferences
    if (expected_code and hasattr(exception, "error_code")) and (
        exception.error_code != expected_code
    ):
        msg = f"Expected error code {expected_code}, got {exception.error_code}"
        raise AssertionError(msg)
