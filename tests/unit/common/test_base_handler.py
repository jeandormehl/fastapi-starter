from unittest.mock import Mock

import pytest
from fastapi.requests import Request

from app.common.base_handler import BaseHandler
from app.common.base_request import BaseRequest
from app.common.base_response import BaseResponse


class TestRequest(BaseRequest):
    test_field: str = "test"


class TestResponse(BaseResponse):
    result: str = "success"


class TestHandler(BaseHandler):
    def _handle_internal(self, request: TestRequest) -> TestResponse:
        raise NotImplementedError()


class TestBaseHandler:
    """Test BaseHandler functionality."""

    def test_base_handler_initialization(self):
        """Test BaseHandler can be instantiated."""
        handler = TestHandler()
        assert handler is not None

    @pytest.mark.asyncio
    async def test_base_handler_abstract_methods(self):
        """Test that BaseHandler requires implementation of abstract methods."""
        handler = TestHandler()

        # BaseHandler should have abstract methods that need implementation
        with pytest.raises(NotImplementedError):
            await handler.handle(
                TestRequest(
                    trace_id="trace_id", request_id="request_id", req=Mock(spec=Request)
                )
            )
