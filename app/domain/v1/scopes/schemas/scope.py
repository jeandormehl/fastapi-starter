from pydantic import BaseModel


class ScopeOutput(BaseModel):
    name: str
    description: str
