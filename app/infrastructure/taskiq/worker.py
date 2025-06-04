from taskiq import AsyncBroker

from app.core.container import container

app = container.get_dependency(AsyncBroker)
