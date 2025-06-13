import asyncio
import functools
from collections.abc import Callable
from typing import Any

from kink import di

from app.common.errors.errors import ErrorCode, TaskError
from app.common.logging import get_logger
from app.domain.v1.idempotency.services.idempotency_service import IdempotencyService
from app.infrastructure.database import Database


def idempotent_task(idempotency_key_field: str = "idempotency_key") -> Any:
    """Decorator to make tasks idempotent with error handling."""

    def decorator(task_func: Callable) -> Callable:
        @functools.wraps(task_func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            idempotency_service = di[IdempotencyService]
            logger = get_logger(task_func.__name__)

            # Extract idempotency key
            idempotency_key = kwargs.get(idempotency_key_field)
            if not idempotency_key or not idempotency_service.task_idempotency_enabled:
                return await task_func(*args, **kwargs)

            task_name = task_func.__name__

            # Generate content hash
            content_hash = idempotency_service.generate_task_hash(
                task_name, args, kwargs
            )

            try:
                # Ensure database connectivity
                await Database.connect_db()

                # Check if task already completed
                idempotency_result = await idempotency_service.check_task_idempotency(
                    idempotency_key=idempotency_key,
                    task_name=task_name,
                    content_hash=content_hash,
                )

                if idempotency_result.is_duplicate:
                    logger.info(
                        f"task {task_name} already completed for key {idempotency_key}"
                    )
                    return idempotency_result.cached_response["result"]

                # Execute task with timeout protection
                try:
                    result = await asyncio.wait_for(
                        task_func(*args, **kwargs),
                        timeout=kwargs.get("task_timeout", 300),  # 5 min default
                    )

                except TimeoutError:
                    logger.error(
                        f"task {task_name} timed out for key {idempotency_key}"
                    )

                    raise TaskError(
                        error_code=ErrorCode.TASK_EXECUTION_ERROR,
                        message=f"task {task_name} execution timed out",
                        task_name=task_name,
                    )

                # Cache successful result
                await idempotency_service.cache_task_result(
                    idempotency_key=idempotency_key,
                    task_name=task_name,
                    content_hash=content_hash,
                    task_result=result,
                )

                return result

            except Exception as e:
                logger.error(f"idempotent task {task_name} failed: {e}")
                raise

        return wrapper

    return decorator
