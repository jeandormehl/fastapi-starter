import pytest
from pydantic import ValidationError

from app.core.config import Configuration
from app.core.constants import TESTS_PATH


class TestConfiguration:
    """Test configuration loading and validation."""

    def test_configuration_from_env_file(self):
        """Test configuration loads from .env.test"""

        config = Configuration(
            _env_file=f"{TESTS_PATH}/.env.test",
            app_secret_key="test-secret-key-minimum-length",
            admin_password="test-admin-password",
        )

        assert config.app_name == "Test FastAPI"
        assert config.app_environment == "test"
        assert config.app_debug is True
        assert config.app_timezone == "Africa/Harare"

    def test_configuration_from_env(self, monkeypatch):
        """Test configuration loading from environment variables."""

        monkeypatch.setenv("APP_NAME", "Test App")
        monkeypatch.setenv("APP_ENVIRONMENT", "prod")
        monkeypatch.setenv("APP_DEBUG", "false")
        monkeypatch.setenv("APP_SECRET_KEY", "test-secret-key-from-env")
        monkeypatch.setenv("ADMIN_PASSWORD", "admin-password-from-env")

        config = Configuration(_env_file=None)

        assert config.app_name == "Test App"
        assert config.app_environment == "prod"
        assert config.app_debug is False
        assert config.app_secret_key.get_secret_value() == "test-secret-key-from-env"

    def test_secret_key_validation(self):
        """Test secret key validation."""

        with pytest.raises(ValidationError):
            Configuration(
                app_secret_key="short",  # Too short
                admin_password="test-password",
            )

    def test_configuration_field_types(self):
        """Test configuration field type validation."""

        config = Configuration(
            app_secret_key="test-secret-key-for-type-validation",
            admin_password="test-password",
            api_port="9000",  # String that should convert to int
            log_to_file="false",
        )

        assert isinstance(config.api_port, int)
        assert config.api_port == 9000
        assert isinstance(config.log_to_file, bool)
        assert config.log_to_file is False

    def test_timezone_validation(self):
        """Test timezone field validation."""

        with pytest.raises(ValidationError):
            Configuration(
                app_secret_key="test-secret-key-for-timezone",
                admin_password="test-password",
                app_timezone="Test/Time_Zone",
            )

        config = Configuration(
            app_secret_key="test-secret-key-for-timezone",
            admin_password="test-password",
            app_timezone="America/New_York",
        )

        assert config.app_timezone == "America/New_York"

    @pytest.mark.parametrize(
        ("env", "expected_debug"),
        [
            ("test", True),
            ("local", True),
            ("sandbox", True),
            ("qa", False),
            ("prod", False),
        ],
    )
    def test_environment_specific_defaults(self, env, expected_debug):
        """Test environment-specific default values."""

        config = Configuration(
            app_secret_key="test-secret-key-for-environment",
            admin_password="test-password",
            app_environment=env,
        )

        assert config.app_debug is expected_debug
