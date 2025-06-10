from datetime import UTC, datetime

import jwt
import pytest

from app.domain.v1.auth.schemas.jwt import JWTPayload
from app.domain.v1.auth.services.jwt_service import JWTService


class TestJWTService:
    """Test JWT service functionality."""

    def test_create_access_token(
        self, jwt_service: JWTService, test_jwt_payload: JWTPayload
    ):
        """Test access token creation."""
        token = jwt_service.create_access_token(
            _id=test_jwt_payload.id,
            client_id=test_jwt_payload.client_id,
            scopes=test_jwt_payload.scopes,
        )

        assert isinstance(token, str)
        assert len(token) > 0
        assert token.count(".") == 2  # JWT has 3 parts separated by dots

    def test_verify_access_token_valid(
        self, jwt_service: JWTService, test_jwt_payload: JWTPayload
    ):
        """Test verification of valid access token."""
        token = jwt_service.create_access_token(
            _id=test_jwt_payload.id,
            client_id=test_jwt_payload.client_id,
            scopes=test_jwt_payload.scopes,
        )

        decoded_payload = jwt_service.verify_token(token)

        assert decoded_payload.client_id == test_jwt_payload.client_id
        assert decoded_payload.scopes == test_jwt_payload.scopes

    def test_verify_access_token_invalid(self, jwt_service: JWTService):
        """Test verification of invalid access token."""
        invalid_token = "invalid.token.here"

        with pytest.raises(Exception):  # noqa: B017, PT011
            jwt_service.verify_token(invalid_token)

    def test_verify_access_token_expired(self, jwt_service: JWTService):
        """Test verification of expired access token."""
        # Create payload with past expiry
        expired_payload = JWTPayload(
            id="test-client",
            client_id="test-client",
            exp=int(datetime.now(UTC).timestamp()) - 3600,  # 1 hour ago
            iat=int(datetime.now(UTC).timestamp()) - 7200,  # 2 hours ago
            scopes=["read"],
        )

        token = jwt.encode(
            expired_payload.model_dump(),
            jwt_service.secret_key,
            algorithm=jwt_service.algorithm,
        )

        with pytest.raises(Exception):  # noqa: B017, PT011
            jwt_service.verify_token(token)
