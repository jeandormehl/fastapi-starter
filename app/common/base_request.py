from abc import ABC

from fastapi.requests import Request
from prisma.models import Client
from pydantic import BaseModel
from pydantic_settings import SettingsConfigDict
from pydiator_core.interfaces import BaseRequest as PydiatorBaseRequest

from app.common.base_schemas import TraceModel


class BaseRequest(TraceModel, PydiatorBaseRequest, ABC):
    """Base request class for all domain requests with enhanced tracing."""

    model_config = SettingsConfigDict(arbitrary_types_allowed=True)

    client: Client | None = None
    data: BaseModel | None = None
    req: Request

    @property
    def trace_context(self) -> dict[str, str]:
        """Get trace context for logging and monitoring."""

        return {
            "trace_id": self.trace_id,
            "request_id": self.request_id,
        }

    @property
    def request_info(self) -> dict[str, str]:
        """Get request information for logging."""

        return {
            "method": self.req.method,
            "path": self.req.url.path,
            "url": str(self.req.url),
            "http_client_ip": self.req.client.host if self.req.client else "unknown",
        }

    def get_full_context(self) -> dict[str, str | int]:
        """Get complete context for logging and error handling."""

        context = {
            **self.trace_context,
            **self.request_info,
        }

        if self.client:
            context["client_id"] = getattr(self.client, "id", "unknown")

        return context
