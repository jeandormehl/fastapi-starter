from pathlib import Path

APP_PATH: Path = (Path(__file__).resolve().parent / '..').resolve()
ROOT_PATH: Path = APP_PATH.parent
STATIC_PATH: Path = (APP_PATH / 'static').resolve()
LOGS_PATH: Path = (STATIC_PATH / 'logs').resolve()
TESTS_PATH: Path = (ROOT_PATH / 'tests').resolve()
TMP_PATH: Path = (STATIC_PATH / 'tmp').resolve()
