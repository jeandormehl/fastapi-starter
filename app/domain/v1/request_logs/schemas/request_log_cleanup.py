from pydantic import BaseModel


class RequestLogCleanupOutput(BaseModel):
    success: bool
    total_deleted: int
    cutoff_date: str
    retention_days: int
