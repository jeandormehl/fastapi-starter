from unittest.mock import patch

from fastapi import FastAPI

# noinspection PyProtectedMember
from app.core.application import _v1
from app.core.config import Configuration


# noinspection PyUnresolvedReferences
class TestApplicationFactory:
    """Test application factory function."""

    def test_get_application_returns_fastapi_instance(self, test_config):
        """Test that get_application returns FastAPI instance."""
        with patch("app.common.logging.initialize_logging"):
            app = _v1(test_config)
            assert isinstance(app, FastAPI)
            assert app.title == test_config.app_name
            assert app.description == test_config.app_description

    def test_application_middleware_setup(self, test_config: Configuration):
        """Test that application sets up middleware correctly."""
        with patch("app.common.logging.initialize_logging"):
            app = _v1(test_config)
            # Check that middleware was added
            assert len(app.user_middleware) > 0

    def test_application_router_inclusion(self, test_config: Configuration):
        """Test that application includes API routers."""
        with patch("app.common.logging.initialize_logging"):
            app = _v1(test_config)
            # Check that routes are registered
            route_paths = [route.path for route in app.routes]
            assert any("/health" in path for path in route_paths)
