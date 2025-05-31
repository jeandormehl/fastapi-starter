from abc import ABC
from typing import TypeVar

from pydantic import BaseModel
from pydantic_settings import SettingsConfigDict
from pydiator_core.interfaces import BaseResponse as PydiatorBaseResponse

T = TypeVar("T", bound=BaseModel)


class BaseResponse(BaseModel, PydiatorBaseResponse, ABC):
    """Enhanced base response class for all domain responses."""

    model_config = SettingsConfigDict(arbitrary_types_allowed=True)

    data: BaseModel | None = None
