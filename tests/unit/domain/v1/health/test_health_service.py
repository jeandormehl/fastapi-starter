import asyncio
from unittest.mock import Mock, patch

from app.core.config import Configuration
from app.domain.v1.health.services.health_service import HealthService


class TestHealthService:
    """Test health service functionality."""

    def test_health_service_initialization(self, test_config: Configuration):
        """Test health service initialization."""
        service = HealthService(test_config)
        assert service is not None

    async def test_check_health_basic(self, health_service: HealthService):
        """Test basic health check."""
        result = await asyncio.gather(
            *[
                health_service.check_database_health(),
                health_service.check_taskiq_health(),
                health_service.check_application_health(),
            ]
        )

        assert result is not None
        assert len(result) == 3
        assert result[0]["status"] in ["healthy", "unhealthy"]
        assert result[1]["status"] == "degraded"
        assert result[2]["status"] in ["healthy", "unhealthy"]

    @patch("app.domain.v1.health.services.health_service.Database")
    async def test_check_health_with_database(
        self, mock_db_class, health_service: HealthService
    ):
        """Test health check including database status."""
        mock_db = Mock()
        mock_db.is_connected.return_value = True
        mock_db_class.return_value = mock_db

        result = await health_service.check_database_health()

        assert result["status"] == "unhealthy"
        assert result["details"] == "database connection failed"
