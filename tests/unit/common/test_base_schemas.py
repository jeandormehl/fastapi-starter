from unittest.mock import Mock

from fastapi import Request

from app.common.base_request import BaseRequest
from app.common.base_response import BaseResponse


class TestBaseRequest:
    """Test BaseRequest functionality."""

    def test_base_request_initialization(self):
        """Test BaseRequest initialization."""
        mock_request = Mock(spec=Request)
        base_req = BaseRequest(
            trace_id="test-trace", request_id="test-request", req=mock_request
        )

        assert base_req.trace_id == "test-trace"
        assert base_req.request_id == "test-request"
        assert base_req.req == mock_request

    def test_base_request_optional_fields(self):
        """Test BaseRequest with optional fields."""
        base_req = BaseRequest(
            trace_id="test-trace", request_id="test-request", req=Mock(spec=Request)
        )

        assert base_req.client is None
        assert base_req.data is None


class TestBaseResponse:
    """Test BaseResponse functionality."""

    def test_base_response_initialization(self):
        """Test BaseResponse initialization."""
        base_resp = BaseResponse(trace_id="test-trace", request_id="test-request")

        assert base_resp.trace_id == "test-trace"
        assert base_resp.request_id == "test-request"

    def test_base_response_optional_fields(self):
        """Test BaseResponse with optional fields."""
        base_resp = BaseResponse(trace_id="test-trace", request_id="test-request")

        assert base_resp.data is None
