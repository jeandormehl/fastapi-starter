from unittest.mock import Mock

import pytest
from fastapi.requests import Request

from app.domain.v1.auth.handlers.client_create_handler import ClientCreateHandler
from app.domain.v1.auth.requests.client_create_request import ClientCreateRequest
from app.domain.v1.auth.schemas import ClientCreateInput


# noinspection PyTestUnpassedFixture
class TestClientCreateHandler:
    """Test client creation handler."""

    @pytest.fixture
    def handler(self):
        """Create handler instance."""
        return ClientCreateHandler()

    @pytest.fixture
    def valid_request(self):
        """Create valid client creation request."""
        return ClientCreateRequest(
            trace_id="test-trace",
            request_id="test-request",
            req=Mock(spec=Request),
            data=ClientCreateInput(
                client_id="new-client",
                client_secret="new-client-secret",
                name="New Test Client",
                scopes=["read", "write"],
            ),
        )

    async def test_handle_duplicate_client_id(
        self,
        handler: ClientCreateHandler,
        valid_request: ClientCreateRequest,
        mock_database: Mock,
    ):
        """Test handling request with duplicate client ID."""
        # Setup mock to return existing client
        mock_database.client.find_unique.return_value = Mock(client_id="new-client")

        with pytest.raises(Exception):  # noqa: B017, PT011
            await handler.handle(valid_request)

    async def test_handle_invalid_scopes(
        self,
        handler: ClientCreateHandler,
        valid_request: ClientCreateRequest,
        mock_database: Mock,
    ):
        """Test handling request with invalid scopes."""
        mock_database.client.find_unique.return_value = None
        mock_database.scope.find_many.return_value = []  # No valid scopes found

        with pytest.raises(Exception):  # noqa: B017, PT011
            await handler.handle(valid_request)
