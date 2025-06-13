from abc import abstractmethod

from prisma.models import Scope

from app.common.base_handler import BaseHandler, TRequest, TResponse
from app.common.errors.errors import ValidationError


class BaseClientHandler(BaseHandler[TRequest, TResponse]):
    @abstractmethod
    async def _handle_internal(self, request: TRequest) -> TResponse:
        """Handle the business logic for this request."""

    async def _validate_scopes(self, scopes: list[str] | None = None) -> list[Scope]:
        if not scopes:
            return []

        try:
            # noinspection PyUnresolvedReferences
            existing_scopes: list[Scope] = await self.db.scope.find_many(
                where={"name": {"in": scopes}}
            )

            existing_scope_names = {scope.name for scope in existing_scopes}
            requested_scope_names = set(scopes)
            missing_scopes = requested_scope_names - existing_scope_names

            if missing_scopes:
                raise ValidationError(
                    message=f"unknown scopes: {', '.join(missing_scopes)}",
                    details={
                        "invalid_scopes": list(missing_scopes),
                        "available_scopes": list(existing_scope_names),
                    },
                )

            return existing_scopes

        except ValidationError:
            raise

        except Exception as e:
            raise ValidationError(
                message="failed to validate scopes",
                details={"error": str(e)},
            ) from e
