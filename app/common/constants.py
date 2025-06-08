from pathlib import Path

# paths
APP_PATH: Path = (Path(__file__).resolve().parent / "..").resolve()
ROOT_PATH: Path = APP_PATH.parent
STATIC_PATH: Path = (APP_PATH / "static").resolve()
TESTS_PATH: Path = (ROOT_PATH / "tests").resolve()

QUARANTINE_ERRORS = {"ClientNotConnectedError"}

SENSITIVE_PATTERNS: set[str] = {
    "password",
    "passwd",
    "pwd",
    "pass",
    "token",
    "access_token",
    "refresh_token",
    "auth_token",
    "secret",
    "key",
    "api_key",
    "private_key",
    "auth",
    "authorization",
    "credential",
    "credentials",
    "ssn",
    "social_security",
    "credit_card",
    "cvv",
    "pin",
}
