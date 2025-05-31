from datetime import datetime, timedelta

import jwt
from kink import di
from pydantic import BaseModel

from app.core.config import Configuration
from app.core.errors.exceptions import AuthenticationException


class JWTPayload(BaseModel):
    id: str
    client_id: str
    exp: int
    iat: int
    scopes: list[str] = []


class JWTService:
    def __init__(self, config: Configuration):
        self.secret_key = config.app_secret_key.get_secret_value()
        self.algorithm = config.jwt_algorithm
        self.access_token_expire_minutes = config.jwt_access_token_expire_minutes

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
            "type": "access_token",
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
                    msg = f"invalid token: missing {field}"
                    raise AuthenticationException(msg)

            # Validate token type
            if payload.get("type") != "access_token":
                msg = "invalid token type"
                raise AuthenticationException(msg)

            return JWTPayload(
                id=payload["id"],
                client_id=payload["client_id"],
                exp=payload["exp"],
                iat=payload["iat"],
                scopes=payload.get("scopes", []),
            )

        except jwt.ExpiredSignatureError:
            msg = "token has expired"
            raise AuthenticationException(msg)

        except jwt.InvalidTokenError as e:
            print(e)
            msg = "invalid token"
            raise AuthenticationException(msg)

    # noinspection PyBroadException,PyMethodMayBeStatic
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
