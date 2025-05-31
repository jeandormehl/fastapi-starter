import sys

import uvicorn
from fastapi import FastAPI

from app.core.config import Configuration
from app.core.container import container
from app.core.logging import initialize_logging

config = container.get_dependency(Configuration)
initialize_logging(config)

app = container.get_dependency(FastAPI)

if __name__ == "__main__":
    # noinspection PyBroadException
    try:
        uvicorn.run(
            "app.main:app",
            host=config.api_host,
            port=config.api_port,
            reload=config.app_environment == "local",
        )

    except KeyboardInterrupt:
        sys.exit(0)

    except Exception:
        sys.exit(1)
