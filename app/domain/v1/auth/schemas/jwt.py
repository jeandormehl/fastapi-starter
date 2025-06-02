from pydantic import BaseModel


class JWTPayload(BaseModel):
    id: str
    client_id: str
    exp: int
    iat: int
    scopes: list[str] = []
