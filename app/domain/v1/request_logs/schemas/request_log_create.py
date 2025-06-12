from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel


class RequestLogCreateInput(BaseModel):
    trace_id: str
    request_id: str
    auth_method: str | None = None
    authenticated: bool
    body: dict[str, Any] | None = None
    client_id: str | None = None
    client_ip: str | None = None
    content_length: int | None = None
    content_type: str | None = None
    duration_ms: Decimal | None = None
    end_time: datetime | None = None
    error_category: str | None = None
    error_occurred: bool = False
    error_type: str | None = None
    has_bearer_token: bool
    headers: dict[str, Any] | None = None
    logged_at: datetime
    path: str
    path_params: dict[str, Any] | None = None
    query_params: dict[str, Any] | None = None
    request_method: str
    request_url: str
    response_body: dict[str, Any] | list[dict[str, Any]] | None = None
    response_headers: dict[str, Any] | None = None
    response_size: int | None = None
    response_type: str | None = None
    scopes: list[str] | None = None
    start_time: datetime
    status_code: int | None = None
    success: bool
    user_agent: str | None = None


class RequestLogCreateOutput(BaseModel):
    success: bool
    id: str
