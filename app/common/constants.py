from pathlib import Path

# paths
APP_PATH: Path = (Path(__file__).resolve().parent / "..").resolve()
ROOT_PATH: Path = APP_PATH.parent
STATIC_PATH: Path = (APP_PATH / "static").resolve()
TESTS_PATH: Path = (ROOT_PATH / "tests").resolve()

QUARANTINE_ERRORS = {"ClientNotConnectedError"}

SENSITIVE_PATTERNS: set[str] = {
    "access_token",
    "api_key",
    "auth",
    "auth_token",
    "authorization",
    "credential",
    "credentials",
    "credit_card",
    "cvv",
    "key",
    "pass",
    "passwd",
    "password",
    "pin",
    "private_key",
    "pwd",
    "refresh_token",
    "secret",
    "social_security",
    "ssn",
    "token",
}

MODEL_JSON_FIELDS = {
    "RequestLog": {
        "body",
        "headers",
        "path_params",
        "query_params",
        "response_body",
        "response_headers",
    },
    "TaskLog": {
        "task_args",
        "task_error",
        "task_kwargs",
        "task_labels",
        "task_result",
    },
    "IdempotencyCache": {
        "response_body",
        "response_headers",
        "task_result",
    },
    # Add other models as needed
}
