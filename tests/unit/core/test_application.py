from unittest.mock import patch

from fastapi import FastAPI

# noinspection PyProtectedMember
from app.core.application import _v1


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
