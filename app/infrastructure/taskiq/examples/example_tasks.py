from typing import Any

from kink import di
from taskiq import AsyncBroker

broker = di[AsyncBroker]


# Example task with custom configuration
@broker.task(
    "example_processing_task",
)
async def example_processing_task(
    data: dict[str, Any],
    _trace_id: str | None = None,
    _request_id: str | None = None,
) -> dict[str, Any]:
    """Example task with error handling and logging."""

    # Simulate some processing
    import asyncio

    await asyncio.sleep(1)

    # Simulate potential failure
    if data.get("simulate_error"):
        msg = "simulated error for testing"
        raise ValueError(msg)

    return {
        "processed": True,
        "data": data,
        "processing_time": 1.0,
    }


# Critical task with high priority and strict timeout
@broker.task(
    "critical_system_task",
    retry_on_error=True,
    max_retries=1,
    timeout=30,
    delay=10,
    priority=1,
)
async def critical_system_task(
    system_id: str,
    action: str,
    _trace_id: str | None = None,
    _request_id: str | None = None,
) -> dict[str, Any]:
    """Critical system task with minimal retries and strict timeout."""

    # Simulate critical system operation
    import asyncio

    await asyncio.sleep(0.1)

    return {
        "system_id": system_id,
        "action": action,
        "completed": True,
    }


# Bulk processing task
@broker.task(
    "bulk_processing_task",
    retry_on_error=True,
    max_retries=1,
    timeout=600,
    delay=10,
    priority=3,
)
async def bulk_processing_task(
    items: list,
    batch_size: int = 100,
    _trace_id: str | None = None,
    _request_id: str | None = None,
) -> dict[str, Any]:
    """Bulk processing task."""

    processed_items = []

    # Process items in batches
    for i in range(0, len(items), batch_size):
        # noinspection PyPep8
        batch = items[i : i + batch_size]

        # Simulate batch processing
        import asyncio

        await asyncio.sleep(0.1 * len(batch))

        processed_items.extend([f"processed_{item}" for item in batch])

    return {
        "total_items": len(items),
        "processed_items": len(processed_items),
        "batch_size": batch_size,
    }
