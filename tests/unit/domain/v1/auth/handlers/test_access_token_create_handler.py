from unittest.mock import Mock

import bcrypt
import pytest
from fastapi.requests import Request

from app.domain.v1.auth.handlers.access_token_create_handler import (
    AccessTokenCreateHandler,
)
from app.domain.v1.auth.requests.access_token_create_request import (
    AccessTokenCreateRequest,
)
from app.domain.v1.auth.schemas import AccessTokenCreateInput
from tests.utils import DatabaseMockHelper, TestDataFactory


class TestAccessTokenCreateHandler:
    """Test access token creation handler."""

    @pytest.fixture
    def handler(self):
        """Create handler instance."""
        return AccessTokenCreateHandler()

    @pytest.fixture
    def valid_request(self):
        """Create valid access token request."""
        return AccessTokenCreateRequest(
            trace_id="test-trace",
            request_id="test-request",
            req=Mock(spec=Request),
            data=AccessTokenCreateInput(
                client_id="test-client", client_secret="test-secret"
            ),
        )

    async def test_handle_valid_request(
        self,
        handler: AccessTokenCreateHandler,
        valid_request: AccessTokenCreateRequest,
        mock_database: Mock,
    ):
        """Test handling valid access token creation request."""
        # Setup mock client
        test_client = TestDataFactory.create_client(
            client_id="test-client",
            hashed_secret=bcrypt.hashpw(b"test-secret", bcrypt.gensalt()),
            scopes=["read", "write"],
            is_active=True,
        )
        DatabaseMockHelper.setup_client_find_unique(mock_database, test_client)

        response = await handler.handle(valid_request)

        assert response.data.access_token is not None
        assert response.data.token_type == "bearer"
        assert response.data.expires_in > 0
        assert response.data.scopes == "read write"

    async def test_handle_invalid_client(
        self,
        handler: AccessTokenCreateHandler,
        valid_request: AccessTokenCreateRequest,
        mock_database: Mock,
    ):
        """Test handling request with invalid client."""
        DatabaseMockHelper.setup_client_find_unique(mock_database, None)

        with pytest.raises(Exception):  # noqa: B017, PT011
            await handler.handle(valid_request)

    async def test_handle_inactive_client(
        self,
        handler: AccessTokenCreateHandler,
        valid_request: AccessTokenCreateRequest,
        mock_database: Mock,
    ):
        """Test handling request with inactive client."""
        inactive_client = TestDataFactory.create_client(
            client_id="test-client", is_active=False
        )
        DatabaseMockHelper.setup_client_find_unique(mock_database, inactive_client)

        with pytest.raises(Exception):  # noqa: B017, PT011
            await handler.handle(valid_request)
