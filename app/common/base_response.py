from abc import ABC

from pydantic import BaseModel
from pydantic_settings import SettingsConfigDict
from pydiator_core.interfaces import BaseResponse as PydiatorBaseResponse

from app.common.base_schemas import TraceModel


class BaseResponse(TraceModel, PydiatorBaseResponse, ABC):
    """Enhanced base response class for all domain responses."""

    model_config = SettingsConfigDict(arbitrary_types_allowed=True)

    data: BaseModel | None = None
