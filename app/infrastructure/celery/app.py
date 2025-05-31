from celery import Celery

from app.core.config import Configuration
from app.core.constants import ROOT_PATH
from app.core.utils import detect_tasks
from app.infrastructure.celery.base_task import BaseTask


def get_celery(config: Configuration) -> Celery:
    """Create and configure Celery application."""

    app = Celery(
        config.app_name,
        broker=config.celery_broker_url,
        backend=config.celery_result_backend,
        include=detect_tasks(str(ROOT_PATH.resolve())),
    )

    app.conf.update(
        timezone=config.app_timezone,
        enable_utc=True,
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        task_track_started=True,
        task_time_limit=60 * 60,  # 1 hour
        task_soft_time_limit=55 * 60,  # 55 minutes
        worker_prefetch_multiplier=1,
        task_acks_late=True,
        worker_disable_rate_limits=False,
        task_compression="gzip",
        result_compression="gzip",
    )

    # Configure for testing
    if config.celery_task_always_eager:
        app.conf.task_always_eager = True
        app.conf.task_eager_propagates = True

    app.Task = BaseTask

    return app
