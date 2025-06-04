from taskiq import AsyncBroker, TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource
from taskiq_redis import RedisScheduleSource

from app.core.config import Configuration
from app.core.container import container
from app.core.logging import initialize_logging

config = container.get_dependency(Configuration)
initialize_logging(config)

broker = container.get_dependency(AsyncBroker)
sources = [LabelScheduleSource(broker=broker)]

if config.taskiq_broker_type == "redis":
    sources.append(RedisScheduleSource(url=config.taskiq_broker_url.get_secret_value()))


app = TaskiqScheduler(broker=broker, sources=sources)
