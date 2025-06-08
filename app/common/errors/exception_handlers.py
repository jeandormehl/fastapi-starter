import traceback
from datetime import datetime
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from kink import di
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.common.errors.errors import ApplicationError, ErrorCode, ErrorDetail
from app.common.logging import get_logger


def create_error_response(
    error_detail: ErrorDetail,
    status_code: int,
    request: Request | None = None,
) -> JSONResponse:
    """Create a standardized error response with logging."""

    # error logging with more context
    log_context = {
        "trace_id": error_detail.trace_id,
        "request_id": error_detail.request_id,
        "status_code": status_code,
        "error_code": error_detail.code,
        "message": error_detail.message,
        "details": error_detail.details,
    }

    # Add request context if available
    if request:
        log_context.update(
            {
                "request_method": request.method,
                "request_path": request.url.path,
                "request_url": str(request.url),
                "client_ip": request.client.host if request.client else "unknown",
                "user_agent": request.headers.get("user-agent", "unknown"),
            }
        )

    logger = get_logger(__name__)
    logger.bind(**log_context).error("api error response generated")

    return JSONResponse(
        status_code=status_code,
        content=error_detail.model_dump(exclude_none=True),
        headers={
            "X-Trace-ID": error_detail.trace_id or "unknown",
            "X-Request-ID": error_detail.request_id or "unknown",
            "X-Error-Code": error_detail.code,
        },
    )


async def app_exception_handler(
    request: Request, exc: ApplicationError
) -> JSONResponse:
    """Handle custom application exceptions."""

    error_detail = exc.to_error_detail()

    # Log additional context for app exceptions
    logger = get_logger(__name__)
    logger.bind(
        trace_id=error_detail.trace_id,
        request_id=error_detail.request_id,
        exception_type=type(exc).__name__,
        error_code=exc.error_code.value,
    ).warning(f"application exception: {exc.message}")

    return create_error_response(error_detail, exc.status_code, request)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle FastAPI HTTP exceptions with detail."""

    # Map HTTP status codes to error codes
    error_code_map = {
        400: ErrorCode.VALIDATION_ERROR,
        401: ErrorCode.AUTHENTICATION_ERROR,
        403: ErrorCode.AUTHORIZATION_ERROR,
        404: ErrorCode.RESOURCE_NOT_FOUND,
        405: ErrorCode.OPERATION_NOT_ALLOWED,
        422: ErrorCode.VALIDATION_ERROR,
        429: ErrorCode.RATE_LIMIT_EXCEEDED,
        500: ErrorCode.INTERNAL_SERVER_ERROR,
        502: ErrorCode.EXTERNAL_SERVICE_ERROR,
        503: ErrorCode.EXTERNAL_SERVICE_UNAVAILABLE,
        504: ErrorCode.EXTERNAL_SERVICE_TIMEOUT,
    }

    error_code = error_code_map.get(exc.status_code, ErrorCode.INTERNAL_SERVER_ERROR)

    # Create more descriptive error messages
    if exc.status_code == 404:
        message = f"the requested resource '{request.url.path}' was not found"
    elif exc.status_code == 401:
        message = "authentication is required to access this resource"
    elif exc.status_code == 403:
        message = "you do not have permission to access this resource"
    elif exc.status_code == 405:
        message = f"method '{request.method}' is not allowed for this endpoint"
    else:
        message = str(exc.detail)

    # noinspection PyTypeChecker
    error_detail = ErrorDetail(
        code=error_code.value,
        message=message,
        details={
            "original_detail": str(exc.detail),
            "endpoint": request.url.path,
            "method": request.method,
        },
        trace_id=getattr(request.state, "trace_id", "unknown"),
        request_id=getattr(request.state, "request_id", "unknown"),
        timestamp=datetime.now(di["timezone"]).isoformat(),
    )

    return create_error_response(error_detail, exc.status_code, request)


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Handle request validation exceptions with detailed field information."""

    # Transform validation errors into a more user-friendly format
    validation_errors = []
    field_errors = {}

    for error in exc.errors():
        field_path = " -> ".join(str(x) for x in error["loc"][1:])  # Skip 'body' prefix
        field_name = field_path or "root"

        error_info = {
            "field": field_name,
            "message": error["msg"],
            "type": error["type"],
            "input_value": error.get("input"),
        }
        validation_errors.append(error_info)

        # Group errors by field for easier consumption
        if field_name not in field_errors:
            field_errors[field_name] = []
        field_errors[field_name].append(error["msg"])

    error_detail = ErrorDetail(
        code=ErrorCode.VALIDATION_ERROR.value,
        message=f"validation failed for {len(validation_errors)} field(s)",
        details={
            "validation_errors": validation_errors,
            "field_errors": field_errors,
            "total_errors": len(validation_errors),
            "request_body_type": request.headers.get("content-type", "unknown"),
        },
        trace_id=getattr(request.state, "trace_id", "unknown"),
        request_id=getattr(request.state, "request_id", "unknown"),
        timestamp=datetime.now(di["timezone"]).isoformat(),
    )

    return create_error_response(
        error_detail, status.HTTP_422_UNPROCESSABLE_ENTITY, request
    )


async def python_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected Python exceptions with comprehensive logging."""

    # Extract exception details
    exc_traceback = traceback.format_exc()
    exc_type_name = type(exc).__name__
    exc_message = str(exc)

    # exception logging
    exception_context = {
        "trace_id": getattr(request.state, "trace_id", "unknown"),
        "request_id": getattr(request.state, "request_id", "unknown"),
        "exception_type": exc_type_name,
        "exception_message": exc_message,
        "exception_module": getattr(exc.__class__, "__module__", "unknown"),
        "request_method": request.method,
        "request_path": request.url.path,
        "request_url": str(request.url),
        "client_ip": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("user-agent", "unknown"),
        "traceback": exc_traceback,
    }

    logger = get_logger(__name__)
    logger.bind(**exception_context).critical("unhandled exception occurred")

    # Return generic error to client (don't expose internal details)
    error_detail = ErrorDetail(
        code=ErrorCode.INTERNAL_SERVER_ERROR.value,
        message="an unexpected error occurred while processing your request",
        details={
            "error_type": exc_type_name,
            "timestamp": datetime.now(di["timezone"]).isoformat(),
            "support_message": "please contact support if this issue persists",
        },
        trace_id=getattr(request.state, "trace_id", "unknown"),
        request_id=getattr(request.state, "request_id", "unknown"),
        timestamp=datetime.now(di["timezone"]).isoformat(),
    )

    return create_error_response(
        error_detail, status.HTTP_500_INTERNAL_SERVER_ERROR, request
    )


# Exception handler registry for easy registration
EXCEPTION_HANDLERS: dict[Any, Any] = {
    ApplicationError: app_exception_handler,
    HTTPException: http_exception_handler,
    StarletteHTTPException: http_exception_handler,
    RequestValidationError: validation_exception_handler,
    ValidationError: validation_exception_handler,
    Exception: python_exception_handler,
}
