from pydantic import BaseModel


class IdempotencyCacheCleanupOutput(BaseModel):
    success: bool
    total_deleted: int = 0
    message: str | None = None
    timestamp: str
