from kink import di
from taskiq import AsyncBroker, TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource
from taskiq_redis import RedisScheduleSource

from app.core.container import container
from app.infrastructure.taskiq.config import TaskiqConfiguration

config = di[TaskiqConfiguration]
broker = container.get_dependency(AsyncBroker)
sources = [LabelScheduleSource(broker=broker)]

if config.broker_type == "redis":
    sources.append(RedisScheduleSource(url=config.broker_url.get_secret_value()))


app = TaskiqScheduler(broker=broker, sources=sources)
