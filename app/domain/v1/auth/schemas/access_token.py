from pydantic import BaseModel


class AccessTokenCreateInput(BaseModel):
    client_id: str
    client_secret: str


class AccessTokenCreateOutput(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    scopes: str | None = None


class AccessTokenRefreshOutput(AccessTokenCreateOutput): ...
