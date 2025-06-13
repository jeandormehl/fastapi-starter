from kink import di

from app.common.base_handler import BaseHandler
from app.common.errors.errors import ErrorCode, TokenError
from app.domain.v1.auth.requests import AccessTokenRefreshRequest
from app.domain.v1.auth.responses import AccessTokenRefreshResponse
from app.domain.v1.auth.schemas.access_token import AccessTokenRefreshOutput
from app.domain.v1.auth.services import JWTService


class AccessTokenRefreshHandler(BaseHandler):
    def __init__(self) -> None:
        super().__init__()

        self.jwt_service = di[JWTService]

    async def _handle_internal(
        self, request: AccessTokenRefreshRequest
    ) -> AccessTokenRefreshResponse:
        try:
            authorization_header = request.req.headers.get("Authorization")
            if not authorization_header or not authorization_header.startswith(
                "Bearer "
            ):
                raise TokenError(
                    error_code=ErrorCode.TOKEN_INVALID,
                    message="missing or invalid authorization header",
                    token_type="access_token",  # nosec
                    trace_id=request.trace_id,
                    request_id=request.request_id,
                )

            current_token = authorization_header.replace("Bearer ", "")
            payload = self.jwt_service.verify_token(current_token)

            response_data = AccessTokenRefreshOutput(
                access_token=self.jwt_service.refresh_token(current_token),
                token_type="bearer",  # nosec
                expires_in=self.jwt_service.access_token_expire_minutes * 60,
                scopes=" ".join(payload.scopes),
            )

            return AccessTokenRefreshResponse(
                trace_id=request.trace_id,
                request_id=request.request_id,
                data=response_data,
            )

        except TokenError:
            raise

        except Exception as e:
            raise TokenError(
                error_code=ErrorCode.TOKEN_INVALID,
                message="failed to refresh token",
                token_type="access_token",  # nosec
                trace_id=request.trace_id,
                request_id=request.request_id,
            ) from e
