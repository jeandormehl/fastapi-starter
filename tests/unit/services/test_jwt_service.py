import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.config import Configuration
from app.core.errors.exceptions import AuthenticationException
from app.domain.v1.auth.services.jwt_service import JWTPayload, JWTService


class TestJWTService:
    """Test JWT service functionality."""

    @pytest.fixture
    def jwt_config(self):
        """JWT service configuration."""

        return Configuration(
            app_secret_key="test-secret-key-for-jwt-testing-very-long",
            jwt_algorithm="HS256",
            jwt_access_token_expire_minutes=30,
            admin_password="test-password",
        )

    @pytest.fixture
    def jwt_service(self, jwt_config):
        """JWT service instance."""

        return JWTService(jwt_config)

    def test_create_access_token_basic(self, jwt_service):
        """Test basic access token creation."""

        token = jwt_service.create_access_token(_id="user-123", client_id="client-456")

        assert isinstance(token, str)
        assert len(token) > 50  # JWT tokens are typically much longer

        # Decode and verify token
        decoded = jwt.decode(
            token, jwt_service.secret_key, algorithms=[jwt_service.algorithm]
        )

        assert decoded["id"] == "user-123"
        assert decoded["client_id"] == "client-456"
        assert decoded["scopes"] == []
        assert "exp" in decoded
        assert "iat" in decoded

    def test_create_access_token_with_scopes(self, jwt_service):
        """Test access token creation with scopes."""

        scopes = ["read", "write", "admin"]
        token = jwt_service.create_access_token(
            _id="user-123", client_id="client-456", scopes=scopes
        )

        decoded = jwt.decode(
            token, jwt_service.secret_key, algorithms=[jwt_service.algorithm]
        )

        assert decoded["scopes"] == scopes

    def test_create_access_token_expiration(self, jwt_service):
        """Test access token expiration time."""

        before_creation = datetime.now(timezone.utc)
        time.sleep(1)

        token = jwt_service.create_access_token(_id="user-123", client_id="client-456")

        time.sleep(1)
        after_creation = datetime.now(timezone.utc)

        decoded = jwt.decode(
            token, jwt_service.secret_key, algorithms=[jwt_service.algorithm]
        )

        exp_time = datetime.fromtimestamp(decoded["exp"], tz=timezone.utc)
        iat_time = datetime.fromtimestamp(decoded["iat"], tz=timezone.utc)

        assert before_creation <= iat_time <= after_creation

        # Verify expiration is 30 minutes after issued time
        expected_exp = iat_time + timedelta(minutes=30)
        assert (
            abs((exp_time - expected_exp).total_seconds()) < 2
        )  # Allow 2 second variance

    def test_verify_access_token_valid(self, jwt_service):
        """Test verification of valid access token."""

        token = jwt_service.create_access_token(
            _id="user-123", client_id="client-456", scopes=["read"]
        )

        payload = jwt_service.verify_token(token)

        assert isinstance(payload, JWTPayload)
        assert payload.id == "user-123"
        assert payload.client_id == "client-456"
        assert payload.scopes == ["read"]

    def test_verify_access_token_invalid_signature(self, jwt_service):
        """Test verification of token with invalid signature."""

        # Create token with different secret
        wrong_token = jwt.encode(
            {"id": "user-123", "client_id": "client-456"},
            "wrong-secret",
            algorithm="HS256",
        )

        with pytest.raises(AuthenticationException) as exc_info:
            jwt_service.verify_token(wrong_token)

        assert "invalid token" in str(exc_info.value)

    def test_verify_access_token_expired(self, jwt_service):
        """Test verification of expired token."""

        # Create expired token
        past_time = datetime.now(timezone.utc) - timedelta(hours=1)
        expired_payload = {
            "id": "user-123",
            "client_id": "client-456",
            "exp": int(past_time.timestamp()),
            "iat": int((past_time - timedelta(minutes=30)).timestamp()),
            "scopes": [],
        }

        expired_token = jwt.encode(
            expired_payload, jwt_service.secret_key, algorithm=jwt_service.algorithm
        )

        with pytest.raises(AuthenticationException) as exc_info:
            jwt_service.verify_token(expired_token)

        assert "token has expired" in str(exc_info.value)

    def test_verify_access_token_malformed(self, jwt_service):
        """Test verification of malformed token."""

        malformed_tokens = [
            "not.a.jwt.token",
            "invalid-jwt",
            "",
            "header.payload",  # Missing signature
            "a.b.c.d",  # Too many parts
        ]

        for malformed_token in malformed_tokens:
            with pytest.raises(AuthenticationException) as exc_info:
                jwt_service.verify_token(malformed_token)

            assert "invalid token" in str(exc_info.value)

    def test_verify_access_token_missing_claims(self, jwt_service):
        """Test verification of token with missing required claims."""

        # Token missing required claims
        incomplete_payload = {
            "id": "user-123",
            # Missing client_id
            "exp": int(
                (datetime.now(timezone.utc) + timedelta(minutes=30)).timestamp()
            ),
            "iat": int(datetime.now(timezone.utc).timestamp()),
        }

        incomplete_token = jwt.encode(
            incomplete_payload, jwt_service.secret_key, algorithm=jwt_service.algorithm
        )

        with pytest.raises(AuthenticationException) as exc_info:
            jwt_service.verify_token(incomplete_token)

        assert "invalid token" in str(exc_info.value)

    def test_refresh_access_token(self, jwt_service):
        """Test access token refresh."""

        original_token = jwt_service.create_access_token(
            _id="user-123", client_id="client-456", scopes=["read", "write"]
        )

        # Wait a small amount to ensure different iat
        import time

        time.sleep(1)

        new_token = jwt_service.refresh_token(original_token)

        # Verify both tokens are different
        assert new_token != original_token

        # Verify both have same payload except for iat/exp
        original_payload = jwt_service.verify_token(original_token)
        new_payload = jwt_service.verify_token(new_token)

        assert original_payload.id == new_payload.id
        assert original_payload.client_id == new_payload.client_id
        assert original_payload.scopes == new_payload.scopes

        assert new_payload.iat > original_payload.iat
        assert new_payload.exp > original_payload.exp

    def test_refresh_access_token_invalid(self, jwt_service):
        """Test refresh of invalid token."""

        with pytest.raises(AuthenticationException):
            jwt_service.refresh_token("invalid-token")

    @pytest.mark.parametrize("algorithm", ["HS256", "HS384", "HS512"])
    def test_different_algorithms(self, algorithm):
        """Test JWT service with different algorithms."""

        config = Configuration(
            app_secret_key="test-secret-key-for-algorithm-testing-very-long",
            jwt_algorithm=algorithm,
            jwt_access_token_expire_minutes=30,
            admin_password="test-password",
        )
        service = JWTService(config)

        token = service.create_access_token(_id="user-123", client_id="client-456")

        payload = service.verify_token(token)
        assert payload.id == "user-123"
        assert payload.client_id == "client-456"

    class TestJWTPayload:
        """Test JWT payload model."""

        def test_jwt_payload_creation(self):
            """Test JWT payload model creation."""

            payload = JWTPayload(
                id="user-123",
                client_id="client-456",
                exp=1234567890,
                iat=1234567800,
                scopes=["read", "write"],
            )

            assert payload.id == "user-123"
            assert payload.client_id == "client-456"
            assert payload.exp == 1234567890
            assert payload.iat == 1234567800
            assert payload.scopes == ["read", "write"]

        def test_jwt_payload_default_scopes(self):
            """Test JWT payload with default empty scopes."""

            payload = JWTPayload(
                id="user-123", client_id="client-456", exp=1234567890, iat=1234567800
            )

            assert payload.scopes == []

        def test_jwt_payload_validation(self):
            """Test JWT payload validation."""

            from pydantic import ValidationError

            # Test missing required fields
            with pytest.raises(ValidationError):
                JWTPayload(
                    id="user-123",
                    # Missing client_id
                    exp=1234567890,
                    iat=1234567800,
                )

            # Test invalid types
            with pytest.raises(ValidationError):
                JWTPayload(
                    id="user-123",
                    client_id="client-456",
                    exp="not-an-int",  # Should be int
                    iat=1234567800,
                )
