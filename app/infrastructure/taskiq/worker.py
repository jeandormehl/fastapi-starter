from taskiq import AsyncBroker

from app.core.config import Configuration
from app.core.container import container
from app.core.logging import initialize_logging

config = container.get_dependency(Configuration)
initialize_logging(config)

app = container.get_dependency(AsyncBroker)
