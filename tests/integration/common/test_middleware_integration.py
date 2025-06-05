import uuid
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from app.common.middlewares import register_request_middlewares
from app.core.errors.exceptions import ValidationException


class TestMiddlewareIntegration:
    """Integration tests for middleware stack."""

    @pytest.fixture
    def test_app(self, test_config):
        """Create FastAPI app with middleware stack."""

        app = FastAPI()

        @app.get("/test")
        async def test_endpoint():
            return {"message": "success"}

        @app.get("/error")
        async def error_endpoint():
            msg = "Test error"
            raise ValueError(msg)

        @app.get("/app-error")
        async def app_error_endpoint():
            raise ValidationException(message="Validation failed")

        # Register middlewares
        register_request_middlewares(test_config, app)
        return app

    @pytest.fixture
    def client(self, test_app):
        """Create test client."""

        return TestClient(test_app)

    def test_successful_request_middleware_chain(self, client):
        """Test successful request through complete middleware chain."""

        response = client.get("/test")

        assert response.status_code == 200
        assert response.json() == {"message": "success"}

        # Verify tracing headers
        assert "X-Trace-ID" in response.headers
        assert "X-Request-ID" in response.headers

        # Verify security headers
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"

        # Verify performance header
        assert "X-Response-Time" in response.headers
        assert response.headers["X-Response-Time"].endswith("s")

        # Verify trace IDs are valid UUIDs
        uuid.UUID(response.headers["X-Trace-ID"])
        uuid.UUID(response.headers["X-Request-ID"])

    def test_error_handling_middleware_chain(self, client):
        """Test error handling through complete middleware chain."""

        response = client.get("/error")

        assert response.status_code == 500

        # Verify tracing headers are present even in error responses
        assert "X-Trace-ID" in response.headers
        assert "X-Request-ID" in response.headers

        # Verify security headers are present
        assert "X-Content-Type-Options" in response.headers

    def test_app_exception_handling_middleware_chain(self, client):
        """Test AppException handling through middleware chain."""

        response = client.get("/app-error")

        # Should be handled by appropriate exception handler
        assert response.status_code in [400, 422]  # Validation error

        # Verify tracing headers
        assert "X-Trace-ID" in response.headers
        assert "X-Request-ID" in response.headers

    def test_trace_id_propagation(self, client):
        """Test trace ID propagation through middleware chain."""

        trace_id = str(uuid.uuid4())

        response = client.get("/test", headers={"X-Trace-ID": trace_id})

        assert response.status_code == 200

        # Verify trace ID was preserved
        assert response.headers["X-Trace-ID"] == trace_id

        # Verify new request ID was generated
        assert "X-Request-ID" in response.headers
        assert response.headers["X-Request-ID"] != trace_id

    def test_middleware_execution_order(self, test_app):
        """Test that middlewares execute in correct order."""

        execution_order = []

        # Patch middleware methods to track execution
        with (
            patch(
                "app.common.middlewares.tracing_middleware.TracingMiddleware.dispatch"
            ) as mock_tracing,
            patch(
                "app.common.middlewares.logging_middleware.LoggingMiddleware.dispatch"
            ) as mock_logging,
            patch(
                "app.common.middlewares.error_middleware.ErrorMiddleware.dispatch"
            ) as mock_error,
        ):
            # Setup mocks to track execution order
            async def track_tracing(request, call_next):
                execution_order.append("tracing")
                return await call_next(request)

            async def track_logging(request, call_next):
                execution_order.append("logging")
                return await call_next(request)

            async def track_error(_request, _call_next):
                execution_order.append("error")
                return JSONResponse({"message": "success"})

            mock_tracing.side_effect = track_tracing
            mock_logging.side_effect = track_logging
            mock_error.side_effect = track_error

            client = TestClient(test_app)
            client.get("/test")

            # Verify execution order (outermost to innermost)
            assert execution_order == ["tracing", "logging", "error"]

    def test_comprehensive_header_collection(self, client):
        """Test comprehensive header collection across middleware stack."""

        response = client.get("/test")

        # Collect all expected headers
        expected_headers = {
            # Tracing headers
            "X-Trace-ID",
            "X-Request-ID",
            # Security headers
            "X-Content-Type-Options",
            "X-Frame-Options",
            "X-XSS-Protection",
            "Strict-Transport-Security",
            # Performance headers
            "X-Response-Time",
        }

        for header in expected_headers:
            assert header in response.headers, f"Missing header: {header}"

    def test_error_context_preservation(self, client):
        """Test that error context is preserved through middleware chain."""

        trace_id = str(uuid.uuid4())

        response = client.get("/error", headers={"X-Trace-ID": trace_id})

        # Even with errors, trace context should be preserved
        assert response.headers["X-Trace-ID"] == trace_id
        assert "X-Request-ID" in response.headers
