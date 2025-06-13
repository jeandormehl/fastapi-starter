from enum import Enum

from app.domain.v1.auth.handlers import (
    AccessTokenCreateHandler,
    AccessTokenRefreshHandler,
    AuthenticatedClientFindHandler,
)
from app.domain.v1.auth.requests import (
    AccessTokenCreateRequest,
    AccessTokenRefreshRequest,
    AuthenticatedClientFindRequest,
)
from app.domain.v1.client.handlers import ClientCreateHandler, ClientUpdateHandler
from app.domain.v1.client.requests import ClientCreateRequest, ClientUpdateRequest
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
from app.domain.v1.scopes.handlers import ScopeFindHandler
from app.domain.v1.scopes.requests import ScopeFindRequest
from app.domain.v1.task_logs.handlers import TaskLogCleanupHandler
from app.domain.v1.task_logs.requests import TaskLogCleanupRequest


class RequestHandlerMap(Enum):
    """Contains all handler registrations"""

    # health
    HEALTCH_CHECK = (HealthCheckRequest, HealthCheckHandler)

    # request_logs
    REQUEST_LOG_CLEANUP = (RequestLogCleanupRequest, RequestLogCleanupHandler)
    REQUEST_LOG_CREATE = (RequestLogCreateRequest, RequestLogCreateHandler)

    # task logs
    TASK_LOG_CLEANUP = (TaskLogCleanupRequest, TaskLogCleanupHandler)

    # auth
    AUTH_ACCESS_TOKEN_CREATE = (AccessTokenCreateRequest, AccessTokenCreateHandler)
    AUTH_ACCESS_TOKEN_REVOKE = (AccessTokenRefreshRequest, AccessTokenRefreshHandler)
    AUTH_AUTHENTICATED_CLIENT_FIND = (
        AuthenticatedClientFindRequest,
        AuthenticatedClientFindHandler,
    )

    # clients
    CLIENT_CREATE = (ClientCreateRequest, ClientCreateHandler)
    CLIENT_UPDATE = (ClientUpdateRequest, ClientUpdateHandler)

    # scopes
    SCOPE_FIND = (ScopeFindRequest, ScopeFindHandler)
