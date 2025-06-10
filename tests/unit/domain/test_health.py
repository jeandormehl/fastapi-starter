from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestHealthEndpoints:
    """Test suite for health check endpoints"""

    def test_liveness_check_success(self):
        """Test that liveness check returns successful response"""
        response = client.get("/v1/health/liveness")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"
        assert "timestamp" in data

    @patch(
        "app.domain.v1.health.services.health_service.HealthService.check_database_health"
    )
    @patch(
        "app.domain.v1.health.services.health_service.HealthService.check_taskiq_health"
    )
    @patch(
        "app.domain.v1.health.services.health_service.HealthService.check_application_health"
    )
    async def test_health_check_all_healthy(self, mock_app, mock_taskiq, mock_db):
        """Test health check when all services are healthy"""
        # Mock all services as healthy
        mock_db.return_value = {"status": "healthy", "details": "Database OK"}
        mock_taskiq.return_value = {"status": "healthy", "details": "TaskIQ OK"}
        mock_app.return_value = {"status": "healthy", "details": "Application OK"}

        response = client.get("/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "services" in data
        assert data["services"]["database"]["status"] == "healthy"
        assert data["services"]["tasks"]["status"] == "healthy"
        assert data["services"]["application"]["status"] == "healthy"

    @patch(
        "app.domain.v1.health.services.health_service.HealthService.check_database_health"
    )
    @patch(
        "app.domain.v1.health.services.health_service.HealthService.check_taskiq_health"
    )
    @patch(
        "app.domain.v1.health.services.health_service.HealthService.check_application_health"
    )
    async def test_health_check_database_unhealthy(
        self, mock_app, mock_taskiq, mock_db
    ):
        """Test health check when database is unhealthy"""
        # Mock database as unhealthy
        mock_db.return_value = {"status": "unhealthy", "error": "Connection failed"}
        mock_taskiq.return_value = {"status": "healthy", "details": "TaskIQ OK"}
        mock_app.return_value = {"status": "healthy", "details": "Application OK"}

        response = client.get("/v1/health")

        assert response.status_code == 503
        data = response.json()["detail"]
        assert data["status"] == "unhealthy"
        assert data["services"]["database"]["status"] == "unhealthy"
