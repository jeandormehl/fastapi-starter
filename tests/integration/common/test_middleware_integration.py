from unittest.mock import patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.common.errors.errors import ErrorCode
from app.common.middlewares.error_middleware import ErrorMiddleware
from app.common.middlewares.logging_middleware import LoggingMiddleware
from app.common.middlewares.tracing_middleware import TracingMiddleware


@pytest.fixture
def app():
    """Create test FastAPI app with middlewares."""

    app = FastAPI()

    # Add middlewares in correct order
    app.add_middleware(ErrorMiddleware)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(TracingMiddleware)

    @app.get("/test")
    async def test_endpoint():
        return {"message": "success"}

    @app.get("/error")
    async def error_endpoint():
        raise HTTPException(status_code=400, detail="Test error")

    @app.get("/server-error")
    async def server_error_endpoint():
        msg = "Internal server error"
        raise Exception(msg)

    return app


@pytest.fixture
def client(app):
    """Create test client."""

    return TestClient(app)


class TestMiddlewareIntegration:
    """Integration tests for middleware stack."""

    def test_successful_request_flow(self, client):
        """Test complete middleware flow for successful request."""

        response = client.get("/test")

        assert response.status_code == 200
        assert response.json() == {"message": "success"}

        # Check that trace headers are added
        assert "X-Trace-ID" in response.headers
        assert "X-Request-ID" in response.headers
        assert "X-Response-Time" in response.headers

    def test_client_error_handling(self, client):
        """Test middleware handling of client errors."""

        response = client.get("/error")

        assert response.status_code == 400

        # Check that trace headers are added to error response
        assert "X-Trace-ID" in response.headers
        assert "X-Request-ID" in response.headers

        # Check error response format
        error_data = response.json()
        assert "detail" in error_data  # FastAPI default format

    def test_server_error_handling(self, client):
        """Test middleware handling of server errors."""

        response = client.get("/server-error")

        assert response.status_code == 500

        # Check that trace headers are added to error response
        assert "X-Trace-ID" in response.headers
        assert "X-Request-ID" in response.headers

        # Check standardized error response format
        error_data = response.json()
        assert "details" in error_data
        assert "message" in error_data
        assert "code" in error_data
        assert "timestamp" in error_data

    def test_trace_id_propagation(self, client):
        """Test that trace ID is properly propagated through middleware stack."""

        custom_trace_id = "custom-trace-123"
        headers = {"X-Trace-ID": custom_trace_id}

        response = client.get("/test", headers=headers)

        assert response.status_code == 200
        assert response.headers["X-Trace-ID"] == custom_trace_id

    @patch("app.infrastructure.taskiq.task_manager.TaskManager.submit_task")
    def test_logging_middleware_database_submission(self, mock_submit_task, client):
        """Test that logging middleware submits database logging tasks."""

        with patch("app.core.config.Configuration") as mock_config:
            mock_config.return_value.request_logging_enabled = True

            response = client.get("/test")

            assert response.status_code == 200
            mock_submit_task.assert_called_once()

            # Verify task submission parameters
            call_args = mock_submit_task.call_args
            assert call_args[0][0] == "request_log:create"  # Task name
            assert isinstance(call_args[0][1], dict)  # Log data

    def test_middleware_performance_headers(self, client):
        """Test that performance headers are properly added."""

        response = client.get("/test")

        assert response.status_code == 200
        assert "X-Response-Time" in response.headers

        # Response time should be in seconds format
        response_time = response.headers["X-Response-Time"]
        assert response_time.endswith("s")
        assert float(response_time[:-1]) >= 0

    def test_error_middleware_exception_context(self, client):
        """Test that error middleware properly sets exception context."""

        response = client.get("/server-error")

        assert response.status_code == 500

        error_data = response.json()

        # Check that standardized error format is used
        assert error_data["message"].startswith("an unexpected error occurred")
        assert error_data["code"] == ErrorCode.INTERNAL_SERVER_ERROR.value
        assert error_data["trace_id"] == response.headers["X-Trace-ID"]
        assert error_data["request_id"] == response.headers["X-Request-ID"]
        assert "timestamp" in error_data
