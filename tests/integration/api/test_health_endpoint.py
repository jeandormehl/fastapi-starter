import asyncio

import pytest
from fastapi import status

from tests.utils import APITestHelper


class TestHealthEndpoint:
    """Integration tests for health endpoint."""

    @pytest.mark.integration
    async def test_health_check_success(self, async_client, task_manager):
        """Test health check endpoint returns success."""

        await task_manager.start()

        response = await async_client.get("/v1/health")

        await APITestHelper.assert_response_status(response, status.HTTP_200_OK)

        json_data = await APITestHelper.assert_response_json(
            response,
            expected_keys=["status", "timestamp"],
            expected_values={"status": "healthy"},
        )

        assert "timestamp" in json_data
        assert isinstance(json_data["timestamp"], str)

    @pytest.mark.integration
    def test_health_check_sync_client(self, client, task_manager):
        """Test health check with synchronous client."""

        asyncio.run(task_manager.start())

        response = client.get("/v1/health")

        assert response.status_code == status.HTTP_200_OK
        json_data = response.json()
        assert json_data["status"] == "healthy"
        assert "timestamp" in json_data
