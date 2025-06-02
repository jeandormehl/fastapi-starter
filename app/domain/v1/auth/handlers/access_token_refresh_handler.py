from kink import di

from app.domain.common import BaseHandler
from app.domain.v1.auth.requests import AccessTokenRefreshRequest
from app.domain.v1.auth.responses import AccessTokenRefreshResponse
from app.domain.v1.auth.schemas.access_token import AccessTokenRefreshOutput
from app.domain.v1.auth.services import JWTService


class AccessTokenRefreshHandler(BaseHandler):
    def __init__(self):
        super().__init__()

        self.jwt_service = di[JWTService]

    async def _handle_internal(
        self, request: AccessTokenRefreshRequest
    ) -> AccessTokenRefreshResponse:
        try:
            current_token = request.req.headers.get("Authorization").replace(
                "Bearer ", ""
            )
            payload = self.jwt_service.verify_token(current_token)

            return AccessTokenRefreshResponse(
                data=AccessTokenRefreshOutput(
                    access_token=self.jwt_service.refresh_token(current_token),
                    token_type="bearer",
                    expires_in=self.jwt_service.access_token_expire_minutes * 60,
                    scopes=" ".join(payload.scopes),
                )
            )

        except Exception as e:
            raise e
