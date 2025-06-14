from datetime import datetime, timedelta

import jwt
from kink import di
from pydantic import SecretStr

from app.common.errors.errors import ErrorCode, TokenError
from app.core.config.jwt_config import JWTConfiguration
from app.domain.v1.auth.schemas import JWTPayload


# noinspection PyBroadException
class JWTService:
    def __init__(self, secret_key: SecretStr, config: JWTConfiguration) -> None:
        self.secret_key = secret_key.get_secret_value()
        self.algorithm = config.jwt.algorithm
        self.access_token_expire_minutes = config.access_token_expire_minutes

    def create_access_token(
        self, _id: str, client_id: str, scopes: list[str] | None = None
    ) -> str:
        """
        Create a JWT access token with client information and scopes.

        Args:
            _id: The client's unique identifier
            client_id: The client's unique identifier for access requests
            scopes: List of scopes/permissions for the client

        Returns:
            str: Encoded JWT token
        """
        if scopes is None:
            scopes = []

        now = datetime.now(di["timezone"])
        expire = now + timedelta(minutes=self.access_token_expire_minutes)

        payload = {
            "id": _id,
            "client_id": client_id,
            "scopes": scopes,
            "exp": expire,
            "iat": now,
            "type": "access_token",  # nosec
        }

        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def refresh_token(self, token: str) -> str:
        """
        Refresh an existing JWT token by creating a new one with updated expiration.

        Args:
            token: The current JWT token

        Returns:
            str: New JWT token with updated expiration
        """
        # Verify the current token first
        payload = self.verify_token(token)

        # Create a new token with the same payload but new expiration
        return self.create_access_token(
            _id=payload.id,
            client_id=payload.client_id,
            scopes=payload.scopes,
        )

    def verify_token(self, token: str) -> JWTPayload:
        """
        Verify and decode a JWT token.

        Args:
            token: The JWT token to verify

        Returns:
            JWTPayload: Decoded token payload

        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])

            # Validate required fields
            required_fields = ["id", "client_id", "exp", "iat"]
            for field in required_fields:
                if field not in payload:
                    raise TokenError(
                        error_code=ErrorCode.TOKEN_INVALID,
                        message=f"token missing required field: {field}",
                        token_type="access_token",  # nosec
                    )

            # Validate token type
            if payload.get("type") != "access_token":
                raise TokenError(
                    error_code=ErrorCode.TOKEN_INVALID,
                    message="invalid token type",
                    token_type="access_token",  # nosec
                )

            return JWTPayload(
                id=payload["id"],
                client_id=payload["client_id"],
                exp=payload["exp"],
                iat=payload["iat"],
                scopes=payload.get("scopes", []),
            )

        except jwt.ExpiredSignatureError:
            raise TokenError(
                error_code=ErrorCode.TOKEN_EXPIRED,
                message="token has expired",
                token_type="access_token",  # nosec
            )

        except jwt.InvalidTokenError:
            raise TokenError(
                error_code=ErrorCode.TOKEN_INVALID,
                message="invalid token format or signature",
                token_type="access_token",  # nosec
            )

    def extract_scopes(self, token: str) -> list[str]:
        """
        Extract scopes from a JWT token without full verification.
        Useful for FastAPI SecurityScopes dependency.

        Args:
            token: The JWT token

        Returns:
            list[str]: List of scopes from the token
        """

        try:
            # Decode without verification to extract scopes
            payload = jwt.decode(
                token, options={"verify_signature": False, "verify_exp": False}
            )

            return payload.get("scopes", [])

        except Exception:
            return []
