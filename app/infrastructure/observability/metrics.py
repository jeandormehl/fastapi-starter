from collections import OrderedDict
from collections.abc import Callable

from opentelemetry import metrics
from opentelemetry.metrics import Meter

# LRU cache for meters with size limit
_meter_cache: OrderedDict[str, Meter] = OrderedDict()
_MAX_CACHE_SIZE = 100


def get_meter(name: str, version: str | None = None) -> Meter:
    """Get or create a meter instance with LRU caching."""
    cache_key = f"{name}:{version or 'default'}"

    if cache_key in _meter_cache:
        # Move to end (most recently used)
        _meter_cache.move_to_end(cache_key)
        return _meter_cache[cache_key]

    # Create new meter
    meter_provider = metrics.get_meter_provider()
    meter = meter_provider.get_meter(name, version)

    # Add to cache and manage size
    _meter_cache[cache_key] = meter
    if len(_meter_cache) > _MAX_CACHE_SIZE:
        _meter_cache.popitem(last=False)  # Remove oldest

    return meter


def setup_custom_metrics() -> dict[str, Callable]:
    """Setup custom application metrics with error handling."""
    try:
        # Application-level metrics
        app_meter = get_meter("fastapi.application")

        # Request metrics
        request_duration = app_meter.create_histogram(
            name="http_request_duration_ms",
            description="HTTP request duration in milliseconds",
            unit="ms",
        )

        request_counter = app_meter.create_counter(
            name="http_requests_total", description="Total number of HTTP requests"
        )

        # Database metrics
        db_meter = get_meter("application.database")

        connection_pool = db_meter.create_up_down_counter(
            name="db_connections_active",
            description="Number of active database connections",
        )

        # Task metrics
        task_meter = get_meter("application.tasks")

        queue_size = task_meter.create_up_down_counter(
            name="task_queue_size", description="Number of tasks in queue"
        )

        return {
            "request_duration": request_duration,
            "request_counter": request_counter,
            "connection_pool": connection_pool,
            "queue_size": queue_size,
        }
    except Exception as e:
        from app.common.logging import get_logger

        get_logger(__name__).error(f"Failed to setup custom metrics: {e}")
        return {}
