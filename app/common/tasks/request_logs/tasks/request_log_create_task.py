import json
from typing import Any

from kink import di
from pydantic import ValidationError as PydanticValidationError

from app.common.logging import get_logger
from app.infrastructure.database import Database
from app.infrastructure.taskiq.schemas import TaskPriority
from app.infrastructure.taskiq.task_manager import TaskManager

db = di[Database]
tm = di[TaskManager]


@tm.broker.task(
    "request_log:create", max_retries=3, retry_delay=5.0, priority=TaskPriority.LOW
)
async def request_log_create_task(data: dict[str, Any]) -> dict[str, Any]:
    """
    Task for creating request logs with better error handling and validation.

    Args:
        data: Request log data dictionary

    Returns:
        Success result or raises exception for retry
    """
    logger = get_logger(__name__)

    trace_id = data.get("trace_id", "unknown")
    request_id = data.get("request_id", "unknown")

    try:
        await db.connect()

        # Validate and sanitize data
        sanitized_data = await _sanitize_log_data(data)

        # Create database record
        request_log = await db.requestlog.create(data=sanitized_data)

        logger.bind(
            trace_id=trace_id, request_id=request_id, log_id=request_log.id
        ).debug("request log successfully created")

        return {
            "success": True,
            "log_id": request_log.id,
            "trace_id": trace_id,
            "request_id": request_id,
        }

    except PydanticValidationError as e:
        logger.bind(
            trace_id=trace_id, request_id=request_id, validation_errors=e.errors()
        ).error("request log data validation failed")

        # Don't retry validation errors
        return {"success": False, "error": "validation_failed", "details": e.errors()}

    except Exception as e:
        logger.bind(
            trace_id=trace_id,
            request_id=request_id,
            error=str(e),
            error_type=type(e).__name__,
        ).error("failed to create request log")

        # Re-raise for retry mechanism
        raise


async def _sanitize_log_data(data: dict[str, Any]) -> dict[str, Any]:
    """Sanitize and validate log data before database insertion."""

    # Ensure required fields
    required_fields = ["trace_id", "request_id", "method", "path"]
    for field in required_fields:
        if field not in data:
            data[field] = "unknown"

    # Sanitize JSON fields
    json_fields = ["headers", "response_headers", "body", "response_body"]
    for field in json_fields:
        if field in data and data[field] is not None:
            try:
                # Ensure it's valid JSON serializable
                data[field] = json.loads(json.dumps(data[field]))
            except (TypeError, ValueError):
                data[field] = {"error": "invalid_json_data"}

    # Limit string field lengths
    string_limits = {
        "url": 2000,
        "user_agent": 500,
        "error_message": 1000,
        "error_type": 100,
    }

    for field, limit in string_limits.items():
        if field in data and isinstance(data[field], str) and len(data[field]) > limit:
            data[field] = data[field][:limit] + "..."

    return data
