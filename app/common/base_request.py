from abc import ABC

from fastapi.requests import Request
from prisma.models import Client
from pydantic import BaseModel
from pydantic_settings import SettingsConfigDict
from pydiator_core.interfaces import BaseRequest as PydiatorBaseRequest

from app.common.base_schemas import TraceModel


class BaseRequest(TraceModel, PydiatorBaseRequest, ABC):
    """Base request class for all domain requests with tracing."""

    model_config = SettingsConfigDict(arbitrary_types_allowed=True)

    client: Client | None = None
    data: BaseModel | None = None
    req: Request
