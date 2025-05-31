from pathlib import Path

# paths
APP_PATH: Path = (Path(__file__).resolve().parent / "..").resolve()
ROOT_PATH: Path = APP_PATH.parent
STATIC_PATH: Path = (APP_PATH / "static").resolve()
TESTS_PATH: Path = (ROOT_PATH / "tests").resolve()
