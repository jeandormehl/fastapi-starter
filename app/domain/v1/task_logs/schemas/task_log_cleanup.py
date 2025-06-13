from pydantic import BaseModel


class TaskLogCleanupOutput(BaseModel):
    success: bool
    total_deleted: int
    cutoff_date: str
    retention_days: int
