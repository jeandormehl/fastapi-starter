# tests/unit/common/test_utils.py
import json
from unittest.mock import Mock

from fastapi import Request

from app.common.base_request import BaseRequest
from app.common.utils import (
    BodyProcessor,
    ClientIPExtractor,
    DataSanitizer,
    PydiatorBuilder,
    TraceContextExtractor,
)


class TestPydiatorBuilder:
    """Test PydiatorBuilder functionality."""

    def test_build_with_trace_context(self):
        """Test building request with trace context."""
        mock_request = Mock(spec=Request)
        mock_request.state.trace_id = "test-trace-123"
        mock_request.state.request_id = "test-request-456"

        result = PydiatorBuilder.build(
            BaseRequest, mock_request, additional_field="test_value"
        )

        assert result.trace_id == "test-trace-123"
        assert result.request_id == "test-request-456"
        assert result.req == mock_request


class TestDataSanitizer:
    """Test DataSanitizer functionality."""

    def test_sanitize_sensitive_data(self):
        """Test sanitization of sensitive data."""
        sensitive_data = {
            "password": "secret123",
            "token": "bearer_token",
            "api_key": "api_secret",
            "normal_field": "normal_value",
        }

        sanitized = DataSanitizer.sanitize_data(sensitive_data)

        assert sanitized["password"] == "[REDACTED]"
        assert sanitized["token"] == "[REDACTED]"
        assert sanitized["api_key"] == "[REDACTED]"
        assert sanitized["normal_field"] == "normal_value"

    def test_sanitize_nested_data(self):
        """Test sanitization of nested data structures."""
        nested_data = {
            "user": {"name": "John", "password": "secret"},
            "credentials": ["token1", "token2"],
            "auth": {
                "bearer_token": "access_token",
                "password": "<PASSWORD>",
                "expire": 3600,
            },
        }

        sanitized = DataSanitizer.sanitize_data(nested_data)

        assert sanitized["user"]["name"] == "John"
        assert sanitized["user"]["password"] == "[REDACTED]"
        assert isinstance(sanitized["credentials"], list)
        assert isinstance(sanitized["auth"], dict)
        assert sanitized["credentials"][0] == "[REDACTED]"
        assert sanitized["auth"]["bearer_token"] == "[REDACTED]"
        assert sanitized["auth"]["expire"] == 3600

    def test_sanitize_long_strings(self):
        """Test truncation of long strings."""
        long_string = "a" * 2000
        sanitized = DataSanitizer.sanitize_data(long_string, max_length=100)

        assert len(sanitized) <= 120  # 100 + "...[TRUNCATED]"
        assert sanitized.endswith("...[TRUNCATED]")

    def test_sanitize_headers(self):
        """Test header sanitization."""
        headers = {
            "Authorization": "Bearer token123",
            "Content-Type": "application/json",
            "X-API-Key": "secret_key",
        }

        sanitized = DataSanitizer.sanitize_headers(headers)

        assert sanitized["Authorization"] == "[REDACTED]"
        assert sanitized["Content-Type"] == "application/json"
        assert sanitized["X-API-Key"] == "[REDACTED]"


# noinspection PyTestUnpassedFixture
class TestClientIPExtractor:
    """Test ClientIPExtractor functionality."""

    def test_extract_ip_from_x_forwarded_for(self):
        """Test IP extraction from X-Forwarded-For header."""
        mock_request = Mock(spec=Request)
        mock_request.headers = {"x-forwarded-for": "192.168.1.1, 10.0.0.1"}

        ip = ClientIPExtractor.extract_client_ip(mock_request)

        assert ip == "192.168.1.1"

    def test_extract_ip_from_x_real_ip(self):
        """Test IP extraction from X-Real-IP header."""
        mock_request = Mock(spec=Request)
        mock_request.headers = {"x-real-ip": "192.168.1.100"}

        ip = ClientIPExtractor.extract_client_ip(mock_request)

        assert ip == "192.168.1.100"

    def test_extract_ip_from_client_direct(self):
        """Test IP extraction from direct client."""
        mock_request = Mock(spec=Request)
        mock_request.headers = {}
        mock_request.client.host = "127.0.0.1"

        ip = ClientIPExtractor.extract_client_ip(mock_request)

        assert ip == "127.0.0.1"

    def test_extract_ip_fallback_unknown(self):
        """Test IP extraction fallback to unknown."""
        mock_request = Mock(spec=Request)
        mock_request.headers = {}
        mock_request.client = None

        ip = ClientIPExtractor.extract_client_ip(mock_request)

        assert ip == "unknown"


class TestBodyProcessor:
    """Test BodyProcessor functionality."""

    def test_process_json_body(self):
        """Test processing JSON body content."""
        json_data = {"key": "value", "number": 123}
        body = json.dumps(json_data).encode("utf-8")

        result = BodyProcessor.process_body_content(body, "application/json")

        assert result["type"] == "json"
        assert result["content"] == json_data
        assert result["encoding"] == "utf-8"

    def test_process_text_body(self):
        """Test processing plain text body content."""
        text_data = "This is plain text content"
        body = text_data.encode("utf-8")

        result = BodyProcessor.process_body_content(body, "text/plain")

        assert result["type"] == "text"
        assert result["content"] == text_data
        assert result["encoding"] == "utf-8"

    def test_process_binary_body(self):
        """Test processing binary body content."""
        binary_data = b"\x89PNG\r\n\x1a\n"  # PNG signature

        result = BodyProcessor.process_body_content(binary_data, "image/png")

        assert result["type"] == "binary"
        assert result["encoding"] == "base64"
        assert isinstance(result["content"], str)

    def test_process_oversized_body(self):
        """Test processing oversized body content."""
        large_data = "x" * 20000
        body = large_data.encode("utf-8")

        result = BodyProcessor.process_body_content(body, "text/plain", max_size=1000)

        assert result["truncated"] is True
        assert result["original_size"] == 20000
        assert result["captured_size"] == 1000


class TestTraceContextExtractor:
    """Test TraceContextExtractor functionality."""

    def test_get_trace_id_present(self):
        """Test extracting trace ID when present."""
        mock_request = Mock(spec=Request)
        mock_request.state.trace_id = "trace-123"

        trace_id = TraceContextExtractor.get_trace_id(mock_request)

        assert trace_id == "trace-123"

    def test_get_trace_id_missing(self):
        """Test extracting trace ID when missing."""
        mock_request = Mock(spec=Request)
        mock_request.state = Mock()
        del mock_request.state.trace_id

        trace_id = TraceContextExtractor.get_trace_id(mock_request)

        assert trace_id == "unknown"

    def test_get_request_id_present(self):
        """Test extracting request ID when present."""
        mock_request = Mock(spec=Request)
        mock_request.state.request_id = "request-456"

        request_id = TraceContextExtractor.get_request_id(mock_request)

        assert request_id == "request-456"

    def test_get_request_id_missing(self):
        """Test extracting request ID when missing."""
        mock_request = Mock(spec=Request)
        mock_request.state = Mock()
        del mock_request.state.request_id

        request_id = TraceContextExtractor.get_request_id(mock_request)

        assert request_id == "unknown"
