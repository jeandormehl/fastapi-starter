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


class RequestHandlerMap(Enum):
    """Contains all handler registrations"""

    # health
    HEALTCH_CHECK = (HealthCheckRequest, HealthCheckHandler)

    # auth
    AUTH_ACCESS_TOKEN_CREATE = (AccessTokenCreateRequest, AccessTokenCreateHandler)
    AUTH_ACCESS_TOKEN_REVOKE = (AccessTokenRefreshRequest, AccessTokenRefreshHandler)
    AUTH_CLIENT_CREATE = (ClientCreateRequest, ClientCreateHandler)
    AUTH_CLIENT_FIND_AUTHENTICATED = (
        ClientFindAuthenticatedRequest,
        ClientFindAuthenticatedHandler,
    )
    AUTH_SCOPE_FIND = (ScopeFindRequest, ScopeFindHandler)
