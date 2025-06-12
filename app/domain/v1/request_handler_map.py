from enum import Enum

from app.domain.v1.auth.handlers import (
    AccessTokenCreateHandler,
    AccessTokenRefreshHandler,
    ClientCreateHandler,
    ClientFindAuthenticatedHandler,
    ScopeFindHandler,
)
from app.domain.v1.auth.requests import (
    AccessTokenCreateRequest,
    AccessTokenRefreshRequest,
    ClientCreateRequest,
    ClientFindAuthenticatedRequest,
    ScopeFindRequest,
)
from app.domain.v1.health.handlers import HealthCheckHandler
from app.domain.v1.health.requests import HealthCheckRequest
from app.domain.v1.request_logs.handlers import (
    RequestLogCleanupHandler,
    RequestLogCreateHandler,
)
from app.domain.v1.request_logs.requests import (
    RequestLogCleanupRequest,
    RequestLogCreateRequest,
)


class RequestHandlerMap(Enum):
    """Contains all handler registrations"""

    # health
    HEALTCH_CHECK = (HealthCheckRequest, HealthCheckHandler)

    # request_logs
    REQUEST_LOG_CLEANUP = (RequestLogCleanupRequest, RequestLogCleanupHandler)
    REQUEST_LOG_CREATE = (RequestLogCreateRequest, RequestLogCreateHandler)

    # auth
    AUTH_ACCESS_TOKEN_CREATE = (AccessTokenCreateRequest, AccessTokenCreateHandler)
    AUTH_ACCESS_TOKEN_REVOKE = (AccessTokenRefreshRequest, AccessTokenRefreshHandler)
    AUTH_CLIENT_CREATE = (ClientCreateRequest, ClientCreateHandler)
    AUTH_CLIENT_FIND_AUTHENTICATED = (
        ClientFindAuthenticatedRequest,
        ClientFindAuthenticatedHandler,
    )
    AUTH_SCOPE_FIND = (ScopeFindRequest, ScopeFindHandler)
