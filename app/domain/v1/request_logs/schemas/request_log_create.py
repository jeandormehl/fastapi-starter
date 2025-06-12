from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel


class RequestLogCreateInput(BaseModel):
    trace_id: str
    request_id: str
    auth_method: str | None = None
    authenticated: bool
    body: dict[str, Any]
    client_id: str | None = None
    client_ip: str
    content_length: int
    content_type: str
    duration_ms: Decimal
    end_time: datetime
    error_category: str
    error_occurred: bool
    error_type: str
    has_bearer_token: bool
    headers: dict[str, Any]
    logged_at: datetime
    method: str
    path: str
    query_params: dict[str, Any] | None = None
    response_body: dict[str, Any] | None = None
    response_headers: dict[str, Any] | None = None
    response_size: int
    response_type: str
    scopes: list[str]
    start_time: datetime
    status_code: int
    success: bool
    url: str
    user_agent: str


class RequestLogCreateOutput(BaseModel):
    success: bool
    id: str
