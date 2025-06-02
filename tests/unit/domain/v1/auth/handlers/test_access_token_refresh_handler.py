from unittest.mock import patch

import pytest

from app.core.errors.exceptions import AuthenticationException
from app.domain.v1.auth.handlers.access_token_refresh_handler import (
    AccessTokenRefreshHandler,
)
from app.domain.v1.auth.requests import AccessTokenRefreshRequest
from app.domain.v1.auth.schemas import JWTPayload


class TestAccessTokenRefreshHandler:
    """Test suite for AccessTokenRefreshHandler."""

    @pytest.fixture
    def handler(self):
        """Create handler instance."""

        return AccessTokenRefreshHandler()

    @pytest.fixture
    def refresh_request(self, mock_request):
        """Create AccessTokenRefreshRequest."""

        mock_request.headers = {"Authorization": "Bearer test-token"}

        return AccessTokenRefreshRequest(
            trace_id="test-trace-id", request_id="test-request-id", req=mock_request
        )

    @pytest.fixture
    def mock_jwt_payload(self):
        """Create mock JWT payload."""

        return JWTPayload(
            id="client-123",
            client_id="test-client",
            exp=1234567890,
            iat=1234567890,
            scopes=["read", "write"],
        )

    @pytest.mark.asyncio
    async def test_successful_token_refresh(
        self, handler, refresh_request, jwt_service, mock_jwt_payload
    ):
        """Test successful token refresh."""

        # Mock JWT service methods
        with patch.object(jwt_service, "verify_token", return_value=mock_jwt_payload):  # noqa: SIM117
            with patch.object(
                jwt_service, "refresh_token", return_value="new-access-token"
            ):
                jwt_service.access_token_expire_minutes = 30

                # Execute handler
                response = await handler._handle_internal(refresh_request)

                # Verify JWT service calls
                jwt_service.verify_token.assert_called_once_with("test-token")
                jwt_service.refresh_token.assert_called_once_with("test-token")

                # Verify response
                assert response.data.access_token == "new-access-token"
                assert response.data.token_type == "bearer"
                assert response.data.expires_in == 1800
                assert response.data.scopes == "read write"

    @pytest.mark.asyncio
    async def test_missing_authorization_header(self, handler, refresh_request):
        """Test failure when Authorization header is missing."""

        # Remove Authorization header
        # noinspection PyPropertyAccess
        refresh_request.req.headers = {}

        # Execute and expect exception
        with pytest.raises(AttributeError):
            await handler._handle_internal(refresh_request)

    @pytest.mark.asyncio
    async def test_invalid_authorization_header_format(
        self, handler, refresh_request, jwt_service
    ):
        """Test failure with invalid Authorization header format."""

        # Set invalid header format
        # noinspection PyPropertyAccess
        refresh_request.req.headers = {"Authorization": "InvalidFormat token"}

        # This should still work as it just replaces "Bearer "
        jwt_payload = JWTPayload(
            id="client-123",
            client_id="test-client",
            exp=1234567890,
            iat=1234567890,
            scopes=["read"],
        )

        with patch.object(jwt_service, "verify_token", return_value=jwt_payload):  # noqa: SIM117
            with patch.object(jwt_service, "refresh_token", return_value="new-token"):
                jwt_service.access_token_expire_minutes = 30
                await handler._handle_internal(refresh_request)
                jwt_service.verify_token.assert_called_once_with("InvalidFormat token")

    @pytest.mark.asyncio
    async def test_invalid_token_verification(
        self, handler, refresh_request, jwt_service
    ):
        """Test failure when token verification fails."""

        # Mock JWT service to raise exception
        with patch.object(
            jwt_service,
            "verify_token",
            side_effect=AuthenticationException("Invalid token"),
        ):
            # Execute and expect exception propagation
            with pytest.raises(AuthenticationException) as exc_info:
                await handler._handle_internal(refresh_request)

            assert "Invalid token" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_token_refresh_failure(
        self, handler, refresh_request, jwt_service, mock_jwt_payload
    ):
        """Test failure during token refresh."""

        # Mock verification success but refresh failure
        with patch.object(jwt_service, "verify_token", return_value=mock_jwt_payload):  # noqa: SIM117
            with patch.object(
                jwt_service,
                "refresh_token",
                side_effect=AuthenticationException("Refresh failed"),
            ):
                # Execute and expect exception propagation
                with pytest.raises(AuthenticationException) as exc_info:
                    await handler._handle_internal(refresh_request)

                assert "Refresh failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_empty_scopes_handling(self, handler, refresh_request, jwt_service):
        """Test handling of payload with empty scopes."""

        # Create payload with empty scopes
        empty_scopes_payload = JWTPayload(
            id="client-123",
            client_id="test-client",
            exp=1234567890,
            iat=1234567890,
            scopes=[],
        )

        with patch.object(  # noqa: SIM117
            jwt_service, "verify_token", return_value=empty_scopes_payload
        ):
            with patch.object(jwt_service, "refresh_token", return_value="new-token"):
                jwt_service.access_token_expire_minutes = 30

                # Execute handler
                response = await handler._handle_internal(refresh_request)

                # Verify empty scopes are handled correctly
                assert response.data.scopes == ""

    @pytest.mark.asyncio
    async def test_single_scope_handling(self, handler, refresh_request, jwt_service):
        """Test handling of payload with single scope."""

        # Create payload with single scope
        single_scope_payload = JWTPayload(
            id="client-123",
            client_id="test-client",
            exp=1234567890,
            iat=1234567890,
            scopes=["admin"],
        )

        with patch.object(  # noqa: SIM117
            jwt_service, "verify_token", return_value=single_scope_payload
        ):
            with patch.object(jwt_service, "refresh_token", return_value="new-token"):
                jwt_service.access_token_expire_minutes = 30

                # Execute handler
                response = await handler._handle_internal(refresh_request)

                # Verify single scope is handled correctly
                assert response.data.scopes == "admin"
