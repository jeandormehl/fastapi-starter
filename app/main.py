import multiprocessing
from typing import Any

from fastapi import FastAPI
from gunicorn.app.base import BaseApplication  # type: ignore[import-untyped]
from kink import inject

from app.core.config import Configuration
from app.core.container import wire_dependencies

wire_dependencies()


@inject
class StandaloneGunicornApplication(BaseApplication):  # type: ignore[misc]
    def __init__(
        self, application: FastAPI, options: dict[str, Any] | None = None
    ) -> None:
        self.options = options or {}
        self.application = application

        super().__init__()

    def load_config(self) -> None:
        config = {
            key: value
            for key, value in self.options.items()
            if key in self.cfg.settings and value is not None
        }
        for key, value in config.items():
            self.cfg.set(key.lower(), value)

    def load(self) -> FastAPI:
        return self.application


@inject
def run_asgi_gunicorn_server(app: FastAPI, config: Configuration) -> None:
    options = {
        'bind': f'{config.api.host}:{config.api.port}',
        'workers': (
            (multiprocessing.cpu_count() * 2) + 1
            if config.app_environment == 'prod'
            else 1
        ),
        'worker_class': 'uvicorn.workers.UvicornWorker',
        'preload_app': False,
        'timeout': 30,
        'reload': config.app_debug,
    }

    StandaloneGunicornApplication(app, options).run()


if __name__ == '__main__':
    run_asgi_gunicorn_server()  # type: ignore[call-arg]
