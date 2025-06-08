import json
from unittest.mock import Mock

from app.common.utils import (
    BodyProcessor,
    ClientIPExtractor,
    DataSanitizer,
    TraceContextExtractor,
)


class TestDataSanitizer:
    """Test cases for DataSanitizer."""

    def test_sanitize_sensitive_keys(self):
        """Test sanitization of sensitive keys."""

        data = {
            "username": "john_doe",
            "password": "secret123",
            "api_key": "key123",
            "normal_field": "normal_value",
        }

        sanitized = DataSanitizer.sanitize_data(data)

        assert sanitized["username"] == "john_doe"
        assert sanitized["password"] == "[REDACTED]"
        assert sanitized["api_key"] == "[REDACTED]"
        assert sanitized["normal_field"] == "normal_value"

    def test_sanitize_nested_data(self):
        """Test sanitization of nested data structures."""

        data = {
            "user": {"name": "John", "password": "secret"},
            "tokens": ["token1", "token2"],
            "config": {"database": {"password": "dbpass"}},
        }

        sanitized = DataSanitizer.sanitize_data(data)

        assert sanitized["user"]["name"] == "John"
        assert sanitized["user"]["password"] == "[REDACTED]"
        assert sanitized["tokens"] == "[REDACTED]"
        assert sanitized["config"]["database"]["password"] == "[REDACTED]"

    def test_sanitize_long_strings(self):
        """Test truncation of long strings."""
        long_string = "a" * 2000
        data = {"long_field": long_string}

        sanitized = DataSanitizer.sanitize_data(data, max_length=1000)

        assert len(sanitized["long_field"]) == 1000 + len("...[TRUNCATED]")
        assert sanitized["long_field"].endswith("...[TRUNCATED]")

    def test_sanitize_headers(self):
        """Test header sanitization."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer token123",
            "X-API-Key": "secret_key",
            "User-Agent": "Mozilla/5.0",
        }

        sanitized = DataSanitizer.sanitize_headers(headers)

        assert sanitized["Content-Type"] == "application/json"
        assert sanitized["Authorization"] == "[REDACTED]"
        assert sanitized["X-API-Key"] == "[REDACTED]"
        assert sanitized["User-Agent"] == "Mozilla/5.0"


class TestClientIPExtractor:
    """Test cases for ClientIPExtractor."""

    def test_extract_forwarded_for_single_ip(self):
        """Test extraction from X-Forwarded-For with single IP."""
        request = Mock()
        request.headers = {"x-forwarded-for": "192.168.1.1"}
        request.client = None

        ip = ClientIPExtractor.extract_client_ip(request)

        assert ip == "192.168.1.1"

    def test_extract_forwarded_for_multiple_ips(self):
        """Test extraction from X-Forwarded-For with multiple IPs."""
        request = Mock()
        request.headers = {"x-forwarded-for": "192.168.1.1, 10.0.0.1, 172.16.0.1"}
        request.client = None

        ip = ClientIPExtractor.extract_client_ip(request)

        assert ip == "192.168.1.1"  # Should return first IP

    def test_extract_real_ip(self):
        """Test extraction from X-Real-IP header."""
        request = Mock()
        request.headers = {"x-real-ip": "192.168.1.1"}
        request.client = None

        ip = ClientIPExtractor.extract_client_ip(request)

        assert ip == "192.168.1.1"

    def test_extract_client_host(self):
        """Test extraction from client.host."""
        request = Mock()
        request.headers = {}
        request.client = Mock()
        request.client.host = "192.168.1.1"

        ip = ClientIPExtractor.extract_client_ip(request)

        assert ip == "192.168.1.1"

    def test_extract_no_client(self):
        """Test fallback when no client information available."""
        request = Mock()
        request.headers = {}
        request.client = None

        ip = ClientIPExtractor.extract_client_ip(request)

        assert ip == "unknown"


class TestBodyProcessor:
    """Test cases for BodyProcessor."""

    def test_process_json_body(self):
        """Test processing JSON body."""
        data = {"key": "value", "number": 42}
        body = json.dumps(data).encode("utf-8")

        result = BodyProcessor.process_body_content(body, "request")

        assert result["content"] == data
        assert result["type"] == "json"
        assert result["encoding"] == "utf-8"
        assert result["size"] == len(body)

    def test_process_text_body(self):
        """Test processing text body."""
        text = "Hello, World!"
        body = text.encode("utf-8")

        result = BodyProcessor.process_body_content(body, "request")

        assert result["content"] == text
        assert result["type"] == "text"
        assert result["encoding"] == "utf-8"
        assert result["size"] == len(body)

    def test_process_large_body_truncation(self):
        """Test truncation of large bodies."""
        large_text = "a" * 20000
        body = large_text.encode("utf-8")

        result = BodyProcessor.process_body_content(body, "request", max_size=10000)

        assert result["truncated"] is True
        assert result["original_size"] == len(body)
        assert result["captured_size"] == 10000
        assert result["type"] == "request"


class TestTraceContextExtractor:
    """Test cases for TraceContextExtractor."""

    def test_get_trace_id_from_state(self):
        """Test extracting trace ID from request state."""
        request = Mock()
        request.state = Mock()
        request.state.trace_id = "trace-123"

        trace_id = TraceContextExtractor.get_trace_id(request)

        assert trace_id == "trace-123"

    def test_get_trace_id_no_state(self):
        """Test fallback when no state available."""
        request = Mock()
        del request.state  # Remove state attribute

        trace_id = TraceContextExtractor.get_trace_id(request)

        assert trace_id == "unknown"

    def test_get_request_id_from_state(self):
        """Test extracting request ID from request state."""
        request = Mock()
        request.state = Mock()
        request.state.request_id = "request-456"

        request_id = TraceContextExtractor.get_request_id(request)

        assert request_id == "request-456"

    def test_get_request_id_no_state(self):
        """Test fallback when no state available."""
        request = Mock()
        del request.state

        request_id = TraceContextExtractor.get_request_id(request)

        assert request_id == "unknown"
