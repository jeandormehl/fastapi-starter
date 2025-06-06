from datetime import datetime
from unittest.mock import Mock, patch

import pytest
from fastapi.security import HTTPAuthorizationCredentials, SecurityScopes
from prisma.models import Client, Scope

from app.core.errors.errors import (
    AppError,
    AuthenticationError,
    AuthorizationError,
    ErrorCode,
)
from app.domain.v1.auth.dependencies import (
    AuthenticationDependency,
    RequireScopes,
    get_client,
    require_admin_scope,
    require_read_scope,
    require_write_scope,
)
from app.domain.v1.auth.schemas import JWTPayload


class TestAuthenticationDependency:
    """Test the main authentication dependency class."""

    @pytest.fixture
    def auth_dependency(self):
        """Create an authentication dependency instance."""

        return AuthenticationDependency()

    @pytest.fixture
    def mock_credentials(self):
        """Create mock HTTP authorization credentials."""

        return HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="valid-jwt-token"
        )

    @pytest.fixture
    def mock_security_scopes(self):
        """Create mock security scopes."""

        return SecurityScopes(scopes=["read", "write"])

    @pytest.fixture
    def mock_jwt_payload(self, test_client_model):
        """Create a mock JWT payload."""

        return JWTPayload(
            id=test_client_model.id,
            client_id=test_client_model.client_id,
            exp=1234567890,
            iat=1234567890,
            scopes=["read", "write"],
        )

    @pytest.mark.asyncio
    async def test_authentication_success(
        self,
        auth_dependency,
        mock_credentials,
        mock_security_scopes,
        mock_database,
        jwt_service,
        mock_jwt_payload,
        test_client_model,
    ):
        """Test successful authentication flow."""

        # Mock JWT verification

        with patch.object(jwt_service, "verify_token", return_value=mock_jwt_payload):
            # Mock database query
            mock_database.client.find_unique.return_value = test_client_model

            # Execute authentication
            result = await auth_dependency(mock_security_scopes, mock_credentials)

            # Assertions
            assert result == test_client_model
            mock_database.client.find_unique.assert_called_once_with(
                where={"client_id": test_client_model.client_id},
                include={"scopes": True},
            )

    @pytest.mark.asyncio
    async def test_authentication_invalid_token(
        self,
        auth_dependency,
        mock_credentials,
        mock_security_scopes,
        jwt_service,
    ):
        """Test authentication with invalid token."""

        # Mock JWT verification to raise exception
        with patch.object(  # noqa: SIM117
            jwt_service,
            "verify_token",
            side_effect=AuthenticationError("Invalid token"),
        ):
            with pytest.raises(AuthenticationError):
                await auth_dependency(mock_security_scopes, mock_credentials)

    @pytest.mark.asyncio
    async def test_authentication_insufficient_scopes(
        self,
        auth_dependency,
        mock_credentials,
        jwt_service,
        test_client_model,
    ):
        """Test authentication with insufficient scopes."""

        # Create security scopes requiring admin access
        security_scopes = SecurityScopes(scopes=["admin"])

        # Create payload with only read/write scopes
        jwt_payload = JWTPayload(
            id=test_client_model.id,
            client_id=test_client_model.client_id,
            exp=1234567890,
            iat=1234567890,
            scopes=["read", "write"],
        )

        with patch.object(jwt_service, "verify_token", return_value=jwt_payload):
            with pytest.raises(AuthorizationError) as exc_info:
                await auth_dependency(security_scopes, mock_credentials)

            assert "insufficient permissions" in str(exc_info.value)
            assert exc_info.value.details.get("required_permissions") == ["admin"]

    @pytest.mark.asyncio
    async def test_authentication_client_not_found(
        self,
        auth_dependency,
        mock_credentials,
        mock_security_scopes,
        mock_database,
        jwt_service,
        mock_jwt_payload,
    ):
        """Test authentication when client is not found in database."""

        with patch.object(jwt_service, "verify_token", return_value=mock_jwt_payload):
            # Mock database to return None
            mock_database.client.find_unique.return_value = None

            with pytest.raises(AuthenticationError) as exc_info:
                await auth_dependency(mock_security_scopes, mock_credentials)

            assert "client not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_authentication_inactive_client(
        self,
        auth_dependency,
        mock_credentials,
        mock_security_scopes,
        mock_database,
        jwt_service,
        mock_jwt_payload,
        test_client_inactive,
    ):
        """Test authentication with inactive client."""

        with patch.object(jwt_service, "verify_token", return_value=mock_jwt_payload):
            mock_database.client.find_unique.return_value = test_client_inactive

            with pytest.raises(AuthenticationError) as exc_info:
                await auth_dependency(mock_security_scopes, mock_credentials)

            assert "client account is inactive" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_authentication_database_error(
        self,
        auth_dependency,
        mock_credentials,
        mock_security_scopes,
        mock_database,
        jwt_service,
        mock_jwt_payload,
    ):
        """Test authentication when database operation fails."""

        with patch.object(jwt_service, "verify_token", return_value=mock_jwt_payload):
            # Mock database to raise an exception
            mock_database.client.find_unique.side_effect = Exception("Database error")

            with pytest.raises(AppError) as exc_info:
                await auth_dependency(mock_security_scopes, mock_credentials)

            assert exc_info.value.error_code == ErrorCode.AUTHENTICATION_ERROR
            assert "unknown authentication error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_authentication_no_scopes_required(
        self,
        auth_dependency,
        mock_credentials,
        mock_database,
        jwt_service,
        mock_jwt_payload,
        test_client_model,
    ):
        """Test authentication when no specific scopes are required."""

        # Create security scopes with no required scopes
        security_scopes = SecurityScopes(scopes=[])

        with patch.object(jwt_service, "verify_token", return_value=mock_jwt_payload):
            mock_database.client.find_unique.return_value = test_client_model

            result = await auth_dependency(security_scopes, mock_credentials)

            assert result == test_client_model


class TestGetClient:
    """Test the get_client convenience function."""

    @pytest.mark.asyncio
    async def test_get_client_success(self, test_client_model):
        """Test successful client retrieval."""

        result = await get_client(test_client_model)
        assert result == test_client_model

    @pytest.mark.asyncio
    async def test_get_client_with_mock_dependency(self):
        """Test get_client with mocked authentication dependency."""

        mock_client = Mock(spec=Client)
        mock_client.id = "test-id"
        mock_client.client_id = "test-client-id"

        with patch(
            "app.domain.v1.auth.dependencies.AuthenticationDependency"
        ) as mock_auth:
            mock_auth.return_value = mock_client
            result = await get_client(mock_client)
            assert result == mock_client


class TestRequireScopes:
    """Test the RequireScopes class for scope-based authorization."""

    @pytest.fixture
    def require_read_write(self):
        """Create a RequireScopes instance for read and write."""

        return RequireScopes("read", "write")

    @pytest.fixture
    def require_admin_only(self):
        """Create a RequireScopes instance for admin only."""

        return RequireScopes("admin")

    @pytest.fixture
    def client_with_all_scopes(self, test_timezone):
        """Create a client with all scopes."""

        return Client(
            id="full-access-client",
            client_id="full-access",
            hashed_secret="<PASSWORD>",
            scopes=[
                Scope(id="test-scope-121", name="read", description="Read access"),
                Scope(id="test-scope-122", name="write", description="Write access"),
                Scope(id="test-scope-123", name="admin", description="Admin access"),
            ],
            is_active=True,
            created_at=datetime.now(test_timezone),
            updated_at=datetime.now(test_timezone),
        )

    @pytest.fixture
    def client_with_read_only(self, test_timezone):
        """Create a client with read-only scope."""

        return Client(
            id="read-only-client",
            client_id="read-only",
            hashed_secret="<PASSWORD>",
            scopes=[
                Scope(id="test-scope-121", name="read", description="Read access"),
            ],
            is_active=True,
            created_at=datetime.now(test_timezone),
            updated_at=datetime.now(test_timezone),
        )

    @pytest.mark.asyncio
    async def test_require_scopes_sufficient_permissions(
        self, require_read_write, client_with_all_scopes
    ):
        """Test scope requirement when client has sufficient permissions."""

        security_scopes = SecurityScopes(scopes=["read", "write"])

        result = await require_read_write(client_with_all_scopes, security_scopes)
        assert result == client_with_all_scopes

    @pytest.mark.asyncio
    async def test_require_scopes_insufficient_permissions(
        self, require_admin_only, client_with_read_only
    ):
        """Test scope requirement when client has insufficient permissions."""

        security_scopes = SecurityScopes(scopes=["admin"])

        with pytest.raises(AuthorizationError) as exc_info:
            await require_admin_only(client_with_read_only, security_scopes)

        assert "not enough permissions" in str(exc_info.value)
        assert "admin" in exc_info.value.details.get("required_permissions", [])

    @pytest.mark.asyncio
    async def test_require_scopes_empty_client_scopes(
        self, require_read_write, test_timezone
    ):
        """Test scope requirement when client has no scopes."""

        client_no_scopes = Client(
            id="no-scopes-client",
            client_id="no-scopes",
            scopes=[],
            is_active=True,
            hashed_secret="<PASSWORD>",
            created_at=datetime.now(test_timezone),
            updated_at=datetime.now(test_timezone),
        )

        security_scopes = SecurityScopes(scopes=["read", "write"])

        with pytest.raises(AuthorizationError) as exc_info:
            await require_read_write(client_no_scopes, security_scopes)

        required_permissions = exc_info.value.details.get("required_permissions", [])
        assert "read" in required_permissions
        assert "write" in required_permissions

    @pytest.mark.asyncio
    async def test_require_scopes_partial_permissions(
        self, require_read_write, client_with_read_only
    ):
        """Test scope requirement when client has partial permissions."""

        security_scopes = SecurityScopes(scopes=["read", "write"])

        with pytest.raises(AuthorizationError) as exc_info:
            await require_read_write(client_with_read_only, security_scopes)

        required_permissions = exc_info.value.details.get("required_permissions", [])
        assert "write" in required_permissions
        assert "read" not in required_permissions


class TestPredefinedScopeDependencies:
    """Test the predefined scope dependency instances."""

    @pytest.fixture
    def client_with_read_scope(self, test_timezone):
        """Create a client with read scope."""
        return Client(
            id="read-client",
            client_id="read-client-id",
            scopes=[
                Scope(id="test-scope-121", name="read", description="Read access"),
            ],
            is_active=True,
            hashed_secret="<PASSWORD>",
            created_at=datetime.now(test_timezone),
            updated_at=datetime.now(test_timezone),
        )

    @pytest.fixture
    def client_with_write_scope(self, test_timezone):
        """Create a client with write scope."""

        return Client(
            id="write-client",
            client_id="write-client-id",
            scopes=[
                Scope(id="test-scope-121", name="read", description="Read access"),
                Scope(id="test-scope-122", name="write", description="Write access"),
            ],
            is_active=True,
            hashed_secret="<PASSWORD>",
            created_at=datetime.now(test_timezone),
            updated_at=datetime.now(test_timezone),
        )

    @pytest.fixture
    def client_with_admin_scope(self, test_timezone):
        """Create a client with admin scope."""

        return Client(
            id="admin-client",
            client_id="admin-client-id",
            scopes=[
                Scope(id="test-scope-121", name="read", description="Read access"),
                Scope(id="test-scope-122", name="write", description="Write access"),
                Scope(id="test-scope-123", name="admin", description="Admin access"),
            ],
            is_active=True,
            hashed_secret="<PASSWORD>",
            created_at=datetime.now(test_timezone),
            updated_at=datetime.now(test_timezone),
        )

    @pytest.mark.asyncio
    async def test_require_read_scope_success(self, client_with_read_scope):
        """Test require_read_scope with sufficient permissions."""

        security_scopes = SecurityScopes(scopes=[])
        result = await require_read_scope(client_with_read_scope, security_scopes)
        assert result == client_with_read_scope

    @pytest.mark.asyncio
    async def test_require_write_scope_success(self, client_with_write_scope):
        """Test require_write_scope with sufficient permissions."""

        security_scopes = SecurityScopes(scopes=[])
        result = await require_write_scope(client_with_write_scope, security_scopes)
        assert result == client_with_write_scope

    @pytest.mark.asyncio
    async def test_require_admin_scope_success(self, client_with_admin_scope):
        """Test require_admin_scope with sufficient permissions."""

        security_scopes = SecurityScopes(scopes=[])
        result = await require_admin_scope(client_with_admin_scope, security_scopes)
        assert result == client_with_admin_scope

    @pytest.mark.asyncio
    async def test_require_write_scope_insufficient(self, client_with_read_scope):
        """Test require_write_scope with insufficient permissions."""

        security_scopes = SecurityScopes(scopes=[])

        with pytest.raises(AuthorizationError):
            await require_write_scope(client_with_read_scope, security_scopes)

    @pytest.mark.asyncio
    async def test_require_admin_scope_insufficient(self, client_with_write_scope):
        """Test require_admin_scope with insufficient permissions."""

        security_scopes = SecurityScopes(scopes=[])

        with pytest.raises(AuthorizationError):
            await require_admin_scope(client_with_write_scope, security_scopes)

    @pytest.mark.asyncio
    async def test_predefined_scopes_type_validation(self):
        """Test that predefined scope dependencies are properly configured."""

        assert isinstance(require_read_scope, RequireScopes)
        assert isinstance(require_write_scope, RequireScopes)
        assert isinstance(require_admin_scope, RequireScopes)

        # Test the required scopes are properly set
        assert "read" in require_read_scope.required_scopes
        assert "write" in require_write_scope.required_scopes
        assert "admin" in require_admin_scope.required_scopes
