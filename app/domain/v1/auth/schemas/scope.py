from pydantic import BaseModel


class ScopeOut(BaseModel):
    name: str
    description: str
