from unittest.mock import Mock

import pytest
from prisma.models import Scope

from app.core.errors.errors import DatabaseError, ValidationError
from app.domain.v1.auth.handlers.client_create_handler import ClientCreateHandler
from app.domain.v1.auth.requests import ClientCreateRequest
from app.domain.v1.auth.schemas import ClientCreateInput


class TestClientCreateHandler:
    """Test suite for ClientCreateHandler."""

    @pytest.fixture
    def handler(self):
        """Create handler instance."""

        return ClientCreateHandler()

    @pytest.fixture
    def valid_client_data(self):
        """Create valid client creation data."""

        return ClientCreateInput(
            client_id="new-client-id",
            client_secret="secure-password",
            scopes=["read", "write"],
        )

    @pytest.fixture
    def client_create_request(self, valid_client_data, mock_request):
        """Create ClientCreateRequest."""

        return ClientCreateRequest(
            trace_id="test-trace-id",
            request_id="test-request-id",
            req=mock_request,
            data=valid_client_data,
        )

    @pytest.fixture
    def available_scopes(self):
        """Create available scopes."""
        return [
            Scope(id="scope-1", name="read", description="Read access"),
            Scope(id="scope-2", name="write", description="Write access"),
            Scope(id="scope-3", name="admin", description="Admin access"),
        ]

    @pytest.fixture
    def created_client_mock(self, test_timezone):
        """Create mock client returned from database."""

        from datetime import datetime

        client_mock = Mock()
        client_mock.id = "created-client-123"
        client_mock.client_id = "new-client-id"
        client_mock.name = None
        client_mock.is_active = True
        client_mock.created_at = datetime.now(test_timezone)
        client_mock.updated_at = datetime.now(test_timezone)
        client_mock.model_dump.return_value = {
            "id": "created-client-123",
            "client_id": "new-client-id",
            "name": None,
            "is_active": True,
            "created_at": datetime.now(test_timezone),
            "updated_at": datetime.now(test_timezone),
        }
        return client_mock

    @pytest.mark.asyncio
    async def test_successful_client_creation(
        self,
        handler,
        client_create_request,
        available_scopes,
        created_client_mock,
        mock_database,
    ):
        """Test successful client creation with valid scopes."""

        # Mock scope validation
        mock_database.scope.find_many.return_value = available_scopes[:2]  # read, write

        # Mock client creation
        mock_database.client.create.return_value = created_client_mock

        # Execute handler
        response = await handler._handle_internal(client_create_request)

        # Verify scope validation query
        mock_database.scope.find_many.assert_called_once_with(
            where={"name": {"in": ["read", "write"]}}
        )

        # Verify client creation
        create_call = mock_database.client.create.call_args
        assert create_call[1]["data"]["client_id"] == "new-client-id"
        assert "hashed_secret" in create_call[1]["data"]
        assert create_call[1]["data"]["scopes"] == {
            "connect": [{"id": "scope-1"}, {"id": "scope-2"}]
        }
        assert create_call[1]["include"] == {"scopes": True}

        # Verify response
        assert response.data.client_id == "new-client-id"
        assert response.data.scopes == ["read", "write"]
        assert response.data.is_active

    @pytest.mark.asyncio
    async def test_client_creation_without_scopes(
        self, handler, mock_database, mock_request, created_client_mock
    ):
        """Test client creation without specifying scopes."""

        # Create request without scopes
        client_data = ClientCreateInput(
            client_id="new-client-id", client_secret="secure-password", scopes=[]
        )
        request = ClientCreateRequest(
            trace_id="test-trace-id",
            request_id="test-request-id",
            req=mock_request,
            data=client_data,
        )

        # Mock client creation
        mock_database.client.create.return_value = created_client_mock

        # Execute handler
        response = await handler._handle_internal(request)

        # Verify no scope validation query
        mock_database.scope.find_many.assert_not_called()

        # Verify client creation without scopes
        create_call = mock_database.client.create.call_args
        assert create_call[1]["data"]["scopes"] == {"connect": []}

        # Verify response
        assert response.data.scopes == []

    @pytest.mark.asyncio
    async def test_client_creation_with_empty_scopes(
        self, handler, mock_database, mock_request, created_client_mock
    ):
        """Test client creation with empty scopes list."""

        # Create request with empty scopes
        client_data = ClientCreateInput(
            client_id="new-client-id", client_secret="secure-password", scopes=[]
        )
        request = ClientCreateRequest(
            trace_id="test-trace-id",
            request_id="test-request-id",
            req=mock_request,
            data=client_data,
        )

        # Mock client creation
        mock_database.client.create.return_value = created_client_mock

        # Execute handler
        response = await handler._handle_internal(request)

        # Verify scope validation with empty list
        mock_database.scope.find_many.assert_not_called()

        # Verify response
        assert response.data.scopes == []

    @pytest.mark.asyncio
    async def test_invalid_scopes_validation(
        self, handler, client_create_request, mock_database
    ):
        """Test validation failure with invalid scopes."""

        # Mock scope validation to return only one scope
        mock_database.scope.find_many.return_value = [
            Scope(id="scope-1", name="read", description="Read access")
        ]

        # Execute and expect validation exception
        with pytest.raises(ValidationError) as exc_info:
            await handler._handle_internal(client_create_request)

        assert "unknown scopes" in str(exc_info.value)
        assert exc_info.value.details["scopes"] == ["write"]

    @pytest.mark.asyncio
    async def test_all_scopes_invalid(
        self, handler, client_create_request, mock_database
    ):
        """Test validation failure when all scopes are invalid."""

        # Mock scope validation to return no scopes
        mock_database.scope.find_many.return_value = []

        # Execute and expect validation exception
        with pytest.raises(ValidationError) as exc_info:
            await handler._handle_internal(client_create_request)

        assert "unknown scopes" in str(exc_info.value)
        assert set(exc_info.value.details["scopes"]) == {"read", "write"}

    @pytest.mark.asyncio
    async def test_database_creation_failure(
        self, handler, client_create_request, available_scopes, mock_database
    ):
        """Test database exception when client creation fails."""

        # Mock successful scope validation
        mock_database.scope.find_many.return_value = available_scopes[:2]

        # Mock client creation failure
        mock_database.client.create.return_value = None

        # Execute and expect database exception
        with pytest.raises(DatabaseError) as exc_info:
            await handler._handle_internal(client_create_request)

        assert "could not create client" in str(exc_info.value)
        assert exc_info.value.details["database_operation"] == "create"
        assert exc_info.value.details["table_name"] == "clients"

    @pytest.mark.asyncio
    async def test_database_exception_during_creation(
        self, handler, client_create_request, available_scopes, mock_database
    ):
        """Test exception handling during database creation."""

        # Mock successful scope validation
        mock_database.scope.find_many.return_value = available_scopes[:2]

        # Mock database exception
        mock_database.client.create.side_effect = DatabaseError("Connection error")

        # Execute and expect exception propagation
        with pytest.raises(DatabaseError) as exc_info:
            await handler._handle_internal(client_create_request)

        assert "Connection error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_scope_validation_database_error(
        self, handler, client_create_request, mock_database
    ):
        """Test exception handling during scope validation."""

        # Mock database exception during scope validation
        mock_database.scope.find_many.side_effect = DatabaseError("Scope query failed")

        # Execute and expect exception propagation
        with pytest.raises(DatabaseError) as exc_info:
            await handler._handle_internal(client_create_request)

        assert "Scope query failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_password_hashing(
        self,
        handler,
        client_create_request,
        available_scopes,
        created_client_mock,
        mock_database,
    ):
        """Test that password is properly hashed."""

        import bcrypt

        # Mock scope validation and client creation
        mock_database.scope.find_many.return_value = available_scopes[:2]
        mock_database.client.create.return_value = created_client_mock

        # Execute handler
        await handler._handle_internal(client_create_request)

        # Verify password is hashed
        create_call = mock_database.client.create.call_args
        hashed_secret = create_call[1]["data"]["hashed_secret"]

        # Verify it's a valid bcrypt hash
        assert hashed_secret.startswith("$2b$")

        # Verify original password matches the hash
        assert bcrypt.checkpw(b"secure-password", hashed_secret.encode("utf-8"))
