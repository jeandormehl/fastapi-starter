import pytest
from pydantic import ValidationError

from app.core.config import Configuration


class TestConfiguration:
    """Comprehensive configuration testing."""

    def test_configuration_default_values(self, test_config):
        """Test configuration loads with default values."""
        assert test_config.app_name == "Test FastAPI Starter"
        assert test_config.app_environment == "test"
        assert test_config.app_timezone == "UTC"
        assert not test_config.parseable_enabled
        assert not test_config.request_logging_enabled

    def test_configuration_debug_mode(self, test_config):  # noqa: ARG002
        """Test debug mode detection."""
        test_environments = ["test", "local", "sandbox"]
        prod_environments = ["qa", "prod"]

        for env in test_environments:
            config = Configuration(
                app_environment=env,
                app_secret_key="test-key-12345678",
                admin_password="test-admin-pass",
            )
            assert config.app_debug is True

        for env in prod_environments:
            config = Configuration(
                app_environment=env,
                app_secret_key="test-key-12345678",
                admin_password="test-admin-pass",
            )
            assert config.app_debug is False

    def test_timezone_validation(self):
        """Test timezone validation."""
        with pytest.raises(ValidationError) as exc_info:
            Configuration(
                app_timezone="Invalid/Timezone",
                app_secret_key="test-key-12345678",
                admin_password="test-admin-pass",
            )

        assert "not a valid timezone" in str(exc_info.value)

    def test_environment_validation(self):
        """Test environment validation."""
        valid_environments = ["test", "local", "sandbox", "qa", "prod"]

        for env in valid_environments:
            config = Configuration(
                app_environment=env,
                app_secret_key="test-key-12345678",
                admin_password="test-admin-pass",
            )
            assert config.app_environment == env.lower()

        with pytest.raises(ValidationError) as exc_info:
            Configuration(
                app_environment="invalid",
                app_secret_key="test-key-12345678",
                admin_password="test-admin-pass",
            )

        assert "Environment must be one of" in str(exc_info.value)

    def test_secret_key_validation(self):
        """Test secret key minimum length validation."""
        with pytest.raises(ValidationError) as exc_info:
            Configuration(app_secret_key="short", admin_password="test-admin-pass")

        assert "Value should have at least 16 items after validation" in str(
            exc_info.value
        )

    def test_parseable_auth_header(self, test_config):
        """Test Parseable auth header generation."""
        auth_header = test_config.parseable_auth_header
        assert auth_header.startswith("Basic ")
        assert len(auth_header) > 10  # Basic auth header should be substantial

    @pytest.mark.parametrize(
        ("retention_days", "should_raise"),
        [(0, True), (1, False), (30, False), (365, False), (366, True)],
    )
    def test_retention_days_validation(self, retention_days, should_raise):
        """Test retention days validation."""
        if should_raise:
            with pytest.raises(ValidationError):
                Configuration(
                    request_logging_retention_days=retention_days,
                    app_secret_key="test-key-12345678",
                    admin_password="test-admin-pass",
                )
        else:
            config = Configuration(
                request_logging_retention_days=retention_days,
                app_secret_key="test-key-12345678",
                admin_password="test-admin-pass",
            )
            assert config.request_logging_retention_days == retention_days
