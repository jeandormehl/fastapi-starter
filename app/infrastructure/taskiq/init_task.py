from typing import Any

from kink import di
from taskiq import AsyncBroker

broker = di[AsyncBroker]


@broker.task(task_name="init_task")
async def init_task(
    message: str,
    delay_seconds: int = 1,
    trace_id: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]: ...
