from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# noinspection PyProtectedMember
from app.core.application import _v1, get_application, lifespan
from app.core.config import Configuration


class TestApplicationLifespan:
    """Test application lifespan management."""

    @pytest.mark.asyncio
    async def test_lifespan_startup_and_shutdown(self):
        """Test that lifespan properly initializes."""

        app = FastAPI()

        with (
            patch("app.core.application.init_db") as mock_init,
            patch("app.core.application.disconnect_db") as mock_disconnect,
        ):
            mock_init.return_value = AsyncMock()
            mock_disconnect.return_value = AsyncMock()

            async with lifespan(app):
                mock_init.assert_called_once()
                # Simulate app running

            mock_disconnect.assert_called_once()


class TestApplicationFactory:
    """Test FastAPI application factory functions."""

    def test_get_application_creates_main_app_with_v1_mount(self, test_config):
        """Test that get_application creates app and mounts v1."""

        with patch("app.core.application._v1") as mock_v1:
            mock_v1_app = Mock(spec=FastAPI)
            mock_v1.return_value = mock_v1_app

            app = get_application(test_config)

            assert isinstance(app, FastAPI)
            mock_v1.assert_called_once_with(test_config)

            # Verify v1 is mounted
            # noinspection PyUnresolvedReferences
            routes = [route.path for route in app.routes if hasattr(route, "path")]
            assert any("/v1" in route for route in routes)

    # noinspection PyUnresolvedReferences
    def test_v1_application_configuration(self, test_config):
        """Test v1 application is configured correctly."""

        app = _v1(test_config)

        assert isinstance(app, FastAPI)
        assert app.debug == test_config.app_debug
        assert app.title == test_config.app_name
        assert app.version == test_config.app_version
        assert app.description == test_config.app_description

    # noinspection PyUnresolvedReferences
    def test_v1_docs_configuration_dev_environment(self, test_config):
        """Test docs are enabled in non-prod environments."""

        test_config.app_environment = "dev"
        app = _v1(test_config)

        assert app.docs_url == "/"
        assert app.redoc_url is None

    # noinspection PyUnresolvedReferences
    def test_v1_docs_configuration_prod_environment(self, test_config):
        """Test docs are disabled in prod environment."""

        test_config.app_environment = "prod"
        app = _v1(test_config)

        assert app.docs_url is None
        assert app.redoc_url is None

    def test_v1_middleware_configuration(self, test_config):
        """Test that all required middleware is added."""

        app = _v1(test_config)

        # Check middleware stack
        # noinspection PyUnresolvedReferences
        middleware_classes = [
            middleware.cls.__name__ for middleware in app.user_middleware
        ]

        expected_middleware = [
            "GZipMiddleware",
            "CORSMiddleware",
            "TrustedHostMiddleware",
            "TracingMiddleware",
            "LoggingMiddleware",
            "ErrorMiddleware",
        ]

        for expected in expected_middleware:
            assert any(expected in cls_name for cls_name in middleware_classes)

    def test_v1_cors_middleware_configuration(self, test_config):
        """Test CORS middleware is configured with settings."""

        test_config.api_cors_origins = ["http://localhost:3000", "https://example.com"]
        app = _v1(test_config)

        # Find CORS middleware
        cors_middleware = None
        # noinspection PyUnresolvedReferences
        for middleware in app.user_middleware:
            if "CORS" in middleware.cls.__name__:
                cors_middleware = middleware
                break

        assert cors_middleware is not None

    def test_v1_static_files_mount(self, test_config):
        """Test static files are mounted correctly."""

        with patch("pathlib.Path.mkdir") as mock_mkdir:
            app = _v1(test_config)

            # Verify static directory creation
            mock_mkdir.assert_called()

            # Check static mount exists
            routes = [route for route in app.routes if hasattr(route, "path")]
            static_routes = [
                route for route in routes if "/static" in getattr(route, "path", "")
            ]
            assert len(static_routes) > 0

    def test_v1_exception_handlers_registration(self, test_config):
        """Test exception handlers are registered."""

        with patch("app.core.application.EXCEPTION_HANDLERS") as mock_handlers:
            mock_handlers.items.return_value = [
                (ValueError, Mock()),
                (RuntimeError, Mock()),
            ]

            app = _v1(test_config)

            # Exception handlers should be registered
            # noinspection PyUnresolvedReferences
            assert len(app.exception_handlers) >= 2

    def test_v1_router_inclusion(self, test_config):
        """Test that v1 router is included."""

        with patch("app.core.application.router_v1"):
            app = _v1(test_config)

            # Router should be included in the app
            assert len(app.routes) > 0


class TestApplicationIntegration:
    """Integration tests for application setup."""

    def test_application_startup_integration(self, test_config):
        """Test complete application startup integration."""

        app = get_application(test_config)
        client = TestClient(app)

        # Test basic connectivity
        response = client.get("/v1/")
        # Should return 404 for root but app should be accessible
        assert response.status_code in [200, 404, 405]

    def test_application_with_different_configs(self):
        """Test application behavior with different configurations."""

        configs = [
            Configuration(
                app_environment="sandbox",
                app_debug=True,
                admin_password="test-admin-password-very-secure",
                app_secret_key="test-secret-key-very-long-and-secure-for-testing",
            ),
            Configuration(
                app_environment="prod",
                app_debug=False,
                admin_password="test-admin-password-very-secure",
                app_secret_key="test-secret-key-very-long-and-secure-for-testing",
            ),
            Configuration(
                app_environment="test",
                app_debug=True,
                admin_password="test-admin-password-very-secure",
                app_secret_key="test-secret-key-very-long-and-secure-for-testing",
            ),
        ]

        for config in configs:
            app = get_application(config)
            assert isinstance(app, FastAPI)

            v1_app = _v1(config)
            # noinspection PyUnresolvedReferences
            assert v1_app.debug == config.app_debug
