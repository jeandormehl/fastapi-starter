from kink import di

from app.common.base_handler import BaseHandler
from app.common.logging import get_logger
from app.domain.v1.request_logs.requests import RequestLogCreateRequest
from app.domain.v1.request_logs.responses import RequestLogCreateResponse
from app.infrastructure.database import Database


class RequestLogCreateHandler(BaseHandler):
    def __init__(self) -> None:
        super().__init__()

        self.db = di[Database]
        self.logger = get_logger(__name__)

    async def _handle_internal(
        self, request: RequestLogCreateRequest
    ) -> RequestLogCreateResponse:
        print(request)
