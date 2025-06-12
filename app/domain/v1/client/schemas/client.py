from datetime import datetime

from pydantic import BaseModel


class ClientCreateInput(BaseModel):
    name: str
    client_secret: str
    scopes: list[str]


class ClientCreateOutput(BaseModel):
    client_id: str
    name: str
    is_active: bool
    created_at: datetime
    scopes: list[str]


class ClientUpdateInput(BaseModel):
    is_active: bool
    scopes: list[str]


class ClientUpdateOutput(ClientCreateOutput): ...
