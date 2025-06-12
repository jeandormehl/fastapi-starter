from datetime import datetime
from typing import Any

from pydantic import BaseModel


class RequestLogCreateInput(BaseModel):
    trace_id: str
    request_id: str
    method: str
    url: str
    path: str
    query_params: dict[str, Any] | None = None
    headers: dict[str, Any] | None = None
    body: dict[str, Any] | None = None
    content_type: str | None = None
    content_length: int | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    status_code: int | None = None
    response_headers: dict[str, Any] | None = None
    response_body: dict[str, Any] | None = None
    response_size: int | None = None
    start_time: datetime
    end_time: datetime | None = None
    duration_ms: float | None = None
    authenticated: bool
    client_id: str | None = None
    scopes: list[str] = []
    error_occured: bool = False
    error_type: str | None = None
    error_message: str | None = None
    error_details: dict[str, Any] | None = None


class RequestLogCreateOutput(BaseModel):
    success: bool
    id: str
