import os
import tempfile
from unittest.mock import Mock, patch

import pytest
from fastapi.requests import Request
from pydantic import ValidationError

from app.core.utils import (
    build_pydiator_request,
    detect_tasks,
    extract_client_info,
    sanitize_for_logging,
)
from app.domain.common import BaseRequest


class TestDetectTasks:
    """Test Celery task detection functionality."""

    def test_detect_tasks_with_task_files(self):
        """Test task detection with valid task files."""

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create task directory structure
            task_dir = os.path.join(temp_dir, "app", "some_module", "tasks")
            os.makedirs(task_dir)

            # Create task files
            task_files = ["email_tasks.py", "user_tasks.py", "__init__.py"]
            for task_file in task_files:
                with open(os.path.join(task_dir, task_file), "w") as f:
                    f.write("# Task file")

            tasks = detect_tasks(temp_dir)

            # Should find task files but not __init__.py
            assert len(tasks) == 2
            assert ["app.some_module.tasks.email_tasks" in task for task in tasks]
            assert ["app.some_module.tasks.users_tasks" in task for task in tasks]

    def test_detect_tasks_no_task_directories(self):
        """Test task detection with no task directories."""

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create app directory but no tasks
            app_dir = os.path.join(temp_dir, "app")
            os.makedirs(app_dir)

            tasks = detect_tasks(temp_dir)

            assert tasks == ()

    def test_detect_tasks_empty_task_directory(self):
        """Test task detection with empty task directory."""

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create empty task directory
            task_dir = os.path.join(temp_dir, "app", "tasks")
            os.makedirs(task_dir)

            tasks = detect_tasks(temp_dir)

            assert tasks == ()


class TestBuildPydiatorRequest:
    """Test pydiator request building functionality."""

    class TestRequest(BaseRequest):
        """Test request class for building tests."""

        __test__ = False
        data: dict = {}  # noqa: RUF012

    @pytest.mark.asyncio
    async def test_build_pydiator_request_success(self, mock_request):
        """Test successful request building."""

        request = await build_pydiator_request(
            self.TestRequest, mock_request, data={"test": "data"}
        )

        assert isinstance(request, self.TestRequest)
        assert request.trace_id == "test-trace-id-12345"
        assert request.request_id == "test-request-id-67890"
        assert request.data == {"test": "data"}

    @pytest.mark.asyncio
    async def test_build_pydiator_request_with_fallback_ids(self):
        """Test request building with fallback IDs."""

        mock_req = Mock(spec=Request)
        mock_req.state = Mock()
        # No trace_id or request_id on state

        request = await build_pydiator_request(self.TestRequest, mock_req, data={})

        # Should generate UUIDs as fallbacks
        assert request.trace_id is not None
        assert request.request_id is not None
        assert len(request.trace_id) == 36
        assert len(request.request_id) == 36

    @pytest.mark.asyncio
    async def test_build_pydiator_request_with_exception(self, mock_request):
        """Test request building with validation exception."""

        class InvalidRequest(BaseRequest):
            required_field: str  # This will cause validation error

        with patch("app.core.logging.get_logger") as mock_logger:
            mock_logger_instance = Mock()
            mock_logger.return_value = mock_logger_instance
            mock_logger_instance.bind.return_value = mock_logger_instance

            with pytest.raises(ValidationError):
                await build_pydiator_request(InvalidRequest, mock_request)

            # Should log the error
            mock_logger_instance.error.assert_called_once()


class TestExtractClientInfo:
    """Test client information extraction."""

    def test_extract_client_info_complete(self):
        """Test client info extraction with all headers."""

        mock_req = Mock()
        mock_req.client = Mock()
        mock_req.client.host = "192.168.1.1"
        mock_req.headers = {
            "user-agent": "Mozilla/5.0",
            "referer": "https://example.com",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/json",
        }

        info = extract_client_info(mock_req)

        assert info["client_ip"] == "192.168.1.1"
        assert info["user_agent"] == "Mozilla/5.0"
        assert info["referer"] == "https://example.com"
        assert info["accept_language"] == "en-US,en;q=0.9"
        assert info["content_type"] == "application/json"

    def test_extract_client_info_minimal(self):
        """Test client info extraction with minimal data."""

        mock_req = Mock()
        mock_req.client = None
        mock_req.headers = {}

        info = extract_client_info(mock_req)

        assert info["client_ip"] == "unknown"
        assert info["user_agent"] == "unknown"
        assert info["referer"] == "unknown"
        assert info["accept_language"] == "unknown"
        assert info["content_type"] == "unknown"


class TestSanitizeForLogging:
    """Test data sanitization for logging."""

    def test_sanitize_passwords_and_secrets(self):
        """Test sanitization of sensitive data."""

        data = {
            "username": "testuser",
            "password": "secret123",
            "api_key": "secret-api-key",
            "authorization": "Bearer token",
            "safe_field": "safe_value",
        }

        sanitized = sanitize_for_logging(data)

        assert sanitized["username"] == "testuser"
        assert sanitized["password"] == "[REDACTED]"
        assert sanitized["api_key"] == "[REDACTED]"
        assert sanitized["authorization"] == "[REDACTED]"
        assert sanitized["safe_field"] == "safe_value"

    def test_sanitize_nested_data(self):
        """Test sanitization of nested dictionaries."""

        data = {
            "user": {
                "name": "John",
                "password": "secret",
                "credentials": {"token": "secret-token", "public_key": "public-data"},
                "nested": {"token": "secret-token", "public_cert": "public-data"},
            },
            "safe_data": "safe",
        }

        sanitized = sanitize_for_logging(data)

        assert sanitized["user"]["name"] == "John"
        assert sanitized["user"]["password"] == "[REDACTED]"
        assert sanitized["user"]["credentials"] == "[REDACTED]"
        assert sanitized["user"]["nested"]["token"] == "[REDACTED]"
        assert sanitized["user"]["nested"]["public_cert"] == "public-data"
        assert sanitized["safe_data"] == "safe"

    def test_sanitize_case_insensitive(self):
        """Test case-insensitive sanitization."""
        data = {"PASSWORD": "secret", "Secret": "secret", "API_TOKEN": "token"}

        sanitized = sanitize_for_logging(data)

        assert sanitized["PASSWORD"] == "[REDACTED]"
        assert sanitized["Secret"] == "[REDACTED]"
        assert sanitized["API_TOKEN"] == "[REDACTED]"
