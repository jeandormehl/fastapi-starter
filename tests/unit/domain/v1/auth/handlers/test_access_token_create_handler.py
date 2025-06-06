from datetime import datetime
from unittest.mock import Mock, patch

import pytest
from bcrypt import gensalt, hashpw
from prisma.models import Client, Scope

from app.core.errors.errors import AuthenticationError, DatabaseError
from app.domain.v1.auth.handlers.access_token_create_handler import (
    AccessTokenCreateHandler,
)
from app.domain.v1.auth.requests import AccessTokenCreateRequest
from app.domain.v1.auth.schemas import AccessTokenCreateInput


class TestAccessTokenCreateHandler:
    """Test suite for AccessTokenCreateHandler."""

    @pytest.fixture
    def handler(self):
        """Create handler instance with mocked dependencies."""

        return AccessTokenCreateHandler()

    @pytest.fixture
    def valid_request_data(self):
        """Create valid request data."""

        return AccessTokenCreateInput(
            client_id="test-client-id", client_secret="test-secret"
        )

    @pytest.fixture
    def access_token_request(self, valid_request_data, mock_request):
        """Create AccessTokenCreateRequest."""

        return AccessTokenCreateRequest(
            trace_id="test-trace-id",
            request_id="test-request-id",
            req=mock_request,
            data=valid_request_data,
        )

    @pytest.fixture
    def client_with_scopes(self, test_timezone):
        """Create a client with multiple scopes."""

        hashed_secret = hashpw(b"test-secret", gensalt()).decode("utf-8")

        return Client(
            id="test-client-123",
            client_id="test-client-id",
            hashed_secret=hashed_secret,
            name="Test Client",
            is_active=True,
            scopes=[
                Scope(id="scope-1", name="read", description="Read access"),
                Scope(id="scope-2", name="write", description="Write access"),
            ],
            created_at=datetime.now(test_timezone),
            updated_at=datetime.now(test_timezone),
        )

    @pytest.mark.asyncio
    async def test_successful_token_creation(
        self,
        handler,
        access_token_request,
        client_with_scopes,
        mock_database,
        jwt_service,
    ):
        """Test successful access token creation."""

        # Mock database response
        mock_database.client.find_unique.return_value = client_with_scopes

        # Mock JWT service
        expected_token = "test-access-token"

        with patch.object(
            jwt_service, "create_access_token", return_value=expected_token
        ):
            jwt_service.access_token_expire_minutes = 30

            # Execute handler
            response = await handler._handle_internal(access_token_request)

            # Verify database query
            mock_database.client.find_unique.assert_called_once_with(
                where={"client_id": "test-client-id"}, include={"scopes": True}
            )

            # Verify JWT creation
            jwt_service.create_access_token.assert_called_once_with(
                _id=client_with_scopes.id,
                client_id=client_with_scopes.client_id,
                scopes=["read", "write"],
            )

            # Verify response
            assert response.data.access_token == expected_token
            assert response.data.token_type == "bearer"
            assert response.data.expires_in == 1800  # 30 * 60
            assert response.data.scopes == "read write"

    @pytest.mark.asyncio
    async def test_invalid_client_id(
        self, handler, access_token_request, mock_database
    ):
        """Test authentication failure with invalid client_id."""

        # Mock database to return None
        mock_database.client.find_unique.return_value = None

        # Execute and expect exception
        with pytest.raises(AuthenticationError) as exc_info:
            await handler._handle_internal(access_token_request)

        assert "invalid client credentials" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_invalid_client_secret(
        self, handler, access_token_request, client_with_scopes, mock_database
    ):
        """Test authentication failure with invalid client_secret."""

        # Modify request to have wrong secret
        access_token_request.data.client_secret = "wrong-secret"

        # Mock database response
        mock_database.client.find_unique.return_value = client_with_scopes

        # Execute and expect exception
        with pytest.raises(AuthenticationError) as exc_info:
            await handler._handle_internal(access_token_request)

        assert "invalid client credentials" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_inactive_client(
        self, handler, access_token_request, client_with_scopes, mock_database
    ):
        """Test authentication failure with inactive client."""

        # Make client inactive
        client_with_scopes.is_active = False

        # Mock database response
        mock_database.client.find_unique.return_value = client_with_scopes

        # Execute and expect exception
        with pytest.raises(AuthenticationError) as exc_info:
            await handler._handle_internal(access_token_request)

        assert "client account is inactive" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_client_with_no_scopes(
        self, handler, access_token_request, mock_database, jwt_service, test_timezone
    ):
        """Test token creation for client with no scopes."""

        # Create client without scopes
        hashed_secret = hashpw(b"test-secret", gensalt()).decode("utf-8")
        client_no_scopes = Client(
            id="test-client-123",
            client_id="test-client-id",
            hashed_secret=hashed_secret,
            name="Test Client",
            is_active=True,
            scopes=[],
            created_at=datetime.now(test_timezone),
            updated_at=datetime.now(test_timezone),
        )

        # Mock responses
        mock_database.client.find_unique.return_value = client_no_scopes
        with patch.object(
            jwt_service, "create_access_token", return_value="test-token"
        ):
            jwt_service.access_token_expire_minutes = 30

            # Execute handler
            response = await handler._handle_internal(access_token_request)

            # Verify JWT creation with empty scopes
            jwt_service.create_access_token.assert_called_once_with(
                _id=client_no_scopes.id, client_id=client_no_scopes.client_id, scopes=[]
            )

            # Verify response has no scopes
            assert response.data.scopes is None

    @pytest.mark.asyncio
    async def test_client_with_none_scopes(
        self, handler, access_token_request, mock_database, jwt_service, test_timezone
    ):
        """Test token creation for client with None scopes."""

        # Create client with None scopes
        hashed_secret = hashpw(b"test-secret", gensalt()).decode("utf-8")
        client_none_scopes = Client(
            id="test-client-123",
            client_id="test-client-id",
            hashed_secret=hashed_secret,
            name="Test Client",
            is_active=True,
            scopes=None,
            created_at=datetime.now(test_timezone),
            updated_at=datetime.now(test_timezone),
        )

        # Mock responses
        mock_database.client.find_unique.return_value = client_none_scopes
        with patch.object(
            jwt_service, "create_access_token", return_value="test-token"
        ):
            jwt_service.access_token_expire_minutes = 30

            # Execute handler
            await handler._handle_internal(access_token_request)

            # Verify JWT creation with empty scopes
            jwt_service.create_access_token.assert_called_once_with(
                _id=client_none_scopes.id,
                client_id=client_none_scopes.client_id,
                scopes=[],
            )

    @pytest.mark.asyncio
    async def test_database_exception_propagation(
        self, handler, access_token_request, mock_database
    ):
        """Test that database exceptions are properly propagated."""

        # Mock database to raise exception
        mock_database.client.find_unique.side_effect = DatabaseError("Database error")

        # Execute and expect exception propagation
        with pytest.raises(DatabaseError) as exc_info:
            await handler._handle_internal(access_token_request)

        assert "Database error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_bcrypt_exception_handling(
        self, handler, access_token_request, mock_database
    ):
        """Test handling of bcrypt exceptions."""

        # Create client with invalid hashed secret format
        invalid_client = Mock(spec=Client)
        invalid_client.id = "test-id"
        invalid_client.client_id = "test-client-id"
        invalid_client.hashed_secret = "invalid-hash-format"
        invalid_client.is_active = True
        invalid_client.scopes = []

        mock_database.client.find_unique.return_value = invalid_client

        # Execute and expect exception
        with pytest.raises(Exception):  # noqa: B017, PT011
            await handler._handle_internal(access_token_request)
