import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI, HTTPException
from kink import di
from pydantic import SecretStr
from starlette.testclient import TestClient
from taskiq import InMemoryBroker

from app.common.middlewares import register_request_middlewares
from app.common.middlewares.request_logging_middleware import RequestLoggingMiddleware
from app.core.config import Configuration
from app.infrastructure.database import Database
from app.infrastructure.taskiq.task_manager import TaskManager


@pytest.fixture
def test_config():
    """Test configuration with request logging enabled."""

    config = Mock(spec=Configuration)
    config.app_secret_key = SecretStr("password")
    config.jwt_algorithm = "HS256"
    config.jwt_access_token_expire_minutes = timedelta(minutes=2)
    config.log_level = "DEBUG"
    config.log_enable_json = False
    config.log_to_file = False
    config.log_file_path = "."
    config.api_allowed_hosts = ["*"]
    config.api_cors_origins = ["*"]
    config.parseable_enabled = False
    config.request_logging_enabled = True
    config.request_logging_log_headers = True
    config.request_logging_log_body = True
    config.request_logging_max_body_size = 10000
    config.request_logging_excluded_paths = ["/health", "/metrics"]
    config.request_logging_excluded_methods = ["OPTIONS"]
    config.request_logging_sensitive_headers = ["authorization", "cookie"]
    config.request_logging_retention_days = 1

    return config


@pytest.fixture
def mock_database():
    """Mock database for testing."""

    db = Mock()
    db.requestlog = Mock()
    db.requestlog.create = AsyncMock()
    db.requestlog.delete_many = AsyncMock()
    return db


@pytest.fixture
def test_app(test_config):
    """Create test FastAPI application."""
    app = FastAPI()

    @app.get("/test")
    async def test_endpoint():
        return {
            "message": "success",
            "timestamp": datetime.now(di["timezone"]).isoformat(),
        }

    @app.post("/test-post")
    async def test_post_endpoint(data: dict[str, Any]):
        return {"received": data, "processed": True}

    @app.get("/error")
    async def error_endpoint():
        raise HTTPException(status_code=400, detail="Test error")

    @app.get("/health")
    async def health_endpoint():
        return {"status": "healthy"}

    # Register middlewares
    register_request_middlewares(test_config, app)
    return app


@pytest.fixture
def client(test_app):
    """Create test client."""

    return TestClient(test_app)


class TestRequestLoggingMiddlewareIntegration:
    """Comprehensive integration tests for request logging middleware."""

    @pytest.fixture
    def mock_task_manager(self):
        """Mock task manager for testing."""

        task_manager = Mock(spec=TaskManager)
        task_manager.submit_task = AsyncMock()
        return task_manager

    @pytest.fixture(autouse=True)
    def setup_di(self, test_config, mock_task_manager, mock_database):
        """Setup dependency injection for tests."""

        di.clear_cache()

        di[Configuration] = test_config
        di[TaskManager] = mock_task_manager
        di["timezone"] = ZoneInfo("UTC")
        di[Database] = mock_database

    async def test_successful_get_request_logging(self, client, mock_task_manager):
        """Test successful GET request logging."""
        trace_id = str(uuid.uuid4())

        response = client.get(
            "/test", headers={"X-Trace-ID": trace_id, "User-Agent": "test-client"}
        )

        assert response.status_code == 200
        assert response.headers["X-Trace-ID"] == trace_id

        # Verify task submission
        mock_task_manager.submit_task.assert_called_once()
        call_args = mock_task_manager.submit_task.call_args

        assert call_args[0][0] == "request_log:create"
        log_data = call_args[0][1]

        # Verify basic log data
        assert log_data["trace_id"] == trace_id
        assert log_data["method"] == "GET"
        assert log_data["path"] == "/test"
        assert log_data["status_code"] == 200
        assert "duration_ms" in log_data
        assert "start_time" in log_data
        assert "end_time" in log_data

    async def test_post_request_with_body_logging(self, client, mock_task_manager):
        """Test POST request with body logging."""
        test_data = {"name": "test", "value": 123}

        response = client.post(
            "/test-post", json=test_data, headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 200

        # Verify task submission
        mock_task_manager.submit_task.assert_called_once()
        call_args = mock_task_manager.submit_task.call_args
        log_data = call_args[0][1]

        # Verify body logging
        assert log_data["method"] == "POST"
        assert "body" in log_data
        assert log_data["body"]["type"] == "json"
        assert log_data["body"]["content"] == test_data

    async def test_error_request_logging(self, client, mock_task_manager):
        """Test error request logging."""
        response = client.get("/error")

        assert response.status_code == 400

        # Verify task submission
        mock_task_manager.submit_task.assert_called_once()
        call_args = mock_task_manager.submit_task.call_args
        log_data = call_args[0][1]

        # Verify error logging
        assert log_data["status_code"] == 400
        assert log_data["error_occurred"] is True
        assert log_data["error_category"] == "client_error"

    async def test_excluded_path_not_logged(self, client, mock_task_manager):
        """Test that excluded paths are not logged."""
        response = client.get("/health")

        assert response.status_code == 200

        # Verify no task submission
        mock_task_manager.submit_task.assert_not_called()

    async def test_header_filtering(self, client, mock_task_manager):
        """Test sensitive header filtering."""
        response = client.get(
            "/test",
            headers={
                "Authorization": "Bearer secret-token",
                "X-API-Key": "secret-key",
                "User-Agent": "test-client",
            },
        )

        assert response.status_code == 200

        # Verify task submission
        call_args = mock_task_manager.submit_task.call_args
        log_data = call_args[0][1]

        # Verify header filtering
        headers = log_data["headers"]
        assert headers["authorization"] == "[REDACTED]"
        assert headers["x-api-key"] == "[REDACTED]"
        assert "user-agent" in headers

    async def test_large_body_truncation(self, client, mock_task_manager, test_config):
        """Test large body truncation."""
        # Set small body size limit for testing
        test_config.request_logging_max_body_size = 100

        large_data = {"data": "x" * 200}

        response = client.post("/test-post", json=large_data)

        assert response.status_code == 200

        # Verify task submission
        call_args = mock_task_manager.submit_task.call_args
        log_data = call_args[0][1]

        # Verify body truncation
        body_info = log_data["body"]
        assert body_info["truncated"] is True
        assert body_info["original_size"] > 100

    async def test_middleware_performance_tracking(self, test_app):
        """Test middleware performance tracking."""
        # Get middleware instance
        middleware = None
        for middleware_obj in test_app.user_middleware:
            if isinstance(middleware_obj.cls, type) and issubclass(
                middleware_obj.cls, RequestLoggingMiddleware
            ):
                middleware = middleware_obj.cls(test_app)
                break

        assert middleware is not None

        # Check initial stats
        stats = await middleware.get_middleware_stats()
        assert "total_requests_processed" in stats
        assert "error_rate" in stats

    async def test_concurrent_requests(self, client, mock_task_manager):
        """Test middleware behavior under concurrent requests."""

        async def make_request():
            return client.get("/test")

        # Make multiple concurrent requests
        tasks = [make_request() for _ in range(10)]
        responses = await asyncio.gather(*tasks)

        # Verify all requests succeeded
        for response in responses:
            assert response.status_code == 200

        # Verify all requests were logged
        assert mock_task_manager.submit_task.call_count == 10

    async def test_task_submission_failure_handling(self, client, mock_task_manager):
        """Test handling of task submission failures."""
        # Mock task submission failure
        mock_task_manager.submit_task.side_effect = Exception("Task submission failed")

        # Request should still succeed despite logging failure
        response = client.get("/test")
        assert response.status_code == 200

        # Verify task submission was attempted
        mock_task_manager.submit_task.assert_called_once()


class TestRequestLoggingTasksIntegration:
    """Integration tests for request logging tasks."""

    @pytest.fixture
    def mock_database(self):
        """Mock database for testing."""

        db = Mock()
        db.requestlog = Mock()
        db.requestlog.create = AsyncMock()
        db.requestlog.delete_many = AsyncMock()
        return db

    @pytest.fixture
    def mock_task_manager(self):
        """Mock task manager for testing."""

        task_manager = Mock(spec=TaskManager)
        task_manager.broker = InMemoryBroker()
        task_manager.submit_task = AsyncMock()
        return task_manager

    @pytest.fixture(autouse=True)
    def setup_di(self, test_config, mock_task_manager, mock_database):
        """Setup dependency injection for tests."""

        di.clear_cache()

        di[Configuration] = test_config
        di[TaskManager] = mock_task_manager
        di["timezone"] = ZoneInfo("UTC")
        di[Database] = mock_database

    async def test_request_log_create_task_success(self, mock_database):
        """Test successful request log creation."""

        from app.common.request_logs.tasks.request_log_create_task import (
            request_log_create_task,
        )

        test_data = {
            "trace_id": "test-trace",
            "request_id": "test-request",
            "method": "GET",
            "path": "/test",
            "status_code": 200,
        }

        # Mock successful database creation
        mock_log = Mock()
        mock_log.id = "log-123"
        mock_database.requestlog.create.return_value = mock_log

        # Execute task
        result = await request_log_create_task(test_data)

        # Verify result
        assert result["success"] is True
        assert result["log_id"] == "log-123"
        assert result["trace_id"] == "test-trace"

        # Verify database call
        mock_database.requestlog.create.assert_called_once()

    async def test_request_log_cleanup_task_success(self, mock_database):
        """Test successful request log cleanup."""

        from app.common.request_logs.tasks.request_log_cleanup_task import (
            request_log_cleanup_task,
        )

        # Mock cleanup result
        mock_result = Mock()
        mock_result.count = 150
        mock_database.requestlog.delete_many.return_value = mock_result

        # Execute task
        result = await request_log_cleanup_task()

        # Verify result
        assert result["success"] is True
        assert result["total_deleted"] == 150

        # Verify database call
        mock_database.requestlog.delete_many.assert_called()

        # Ensure the correct parameters are passed
        args, kwargs = mock_database.requestlog.delete_many.call_args
        assert kwargs.get("where", {}).get("created_at", {}).get("lt") is not None
