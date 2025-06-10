from typing import Any

from pydantic import BaseModel


class HealthCheckOutput(BaseModel):
    status: str
    timestamp: str
    duration: float
    services: dict[str, Any]


class HealthLivenessOutput(BaseModel):
    status: str
    timestamp: str
