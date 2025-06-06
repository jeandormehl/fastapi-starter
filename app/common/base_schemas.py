from pydantic import BaseModel


class TraceModel(BaseModel):
    trace_id: str
    request_id: str
