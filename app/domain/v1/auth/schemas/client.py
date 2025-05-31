from datetime import datetime

from pydantic import BaseModel


class ClientOut(BaseModel):
    client_id: str
    is_active: bool
    created_at: datetime
    scopes: list[str]


class ClientCreateInput(BaseModel):
    client_id: str
    client_secret: str
    scopes: list[str]
