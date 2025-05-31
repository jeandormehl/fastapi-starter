import logging
import sys

from celery import Celery

from app.core.config import Configuration
from app.core.container import container
from app.core.logging import initialize_logging

config = container.get_dependency(Configuration)
initialize_logging(config)

app = container.get_dependency(Celery)

if __name__ == "__main__":
    argv = [
        "-A",
        "app.infrastructure.celery.beat:app",
        "beat",
        "-l",
        logging.DEBUG if config.app_environment == "local" else logging.WARNING,
    ]

    try:
        app.start(argv)

    except KeyboardInterrupt:
        print("application stopped by user")
        sys.exit(0)

    except Exception as e:
        print(f"application startup failed: {e}")
        sys.exit(1)
