import sys

import uvicorn
from fastapi import FastAPI

from app.core.config import Configuration
from app.core.container import container

config = container.get_dependency(Configuration)
app = container.get_dependency(FastAPI)

if __name__ == "__main__":
    # noinspection PyBroadException
    try:
        uvicorn.run(
            "app.main:app",
            host=config.api.host,
            port=config.api.port,
            reload=config.app_environment == "local",
        )

    except KeyboardInterrupt:
        sys.exit(0)

    except Exception:
        sys.exit(1)
