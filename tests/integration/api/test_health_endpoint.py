import asyncio

import pytest
from fastapi import status
from httpx import AsyncClient
from starlette.testclient import TestClient

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


class TestHealthEndpointExtended:
    """Extended tests for health endpoint."""

    def test_health_endpoint_sync_client(self, client: TestClient):
        """Test health endpoint with synchronous client."""
        response = client.get("/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] in ["degraded"]

    async def test_health_endpoint_async_client(self, async_client: AsyncClient):
        """Test health endpoint with asynchronous client."""
        response = await async_client.get("/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "timestamp" in data
        assert "version" in data["services"]["application"]

    async def test_health_endpoint_performance(self, async_client: AsyncClient):
        """Test health endpoint performance."""
        import time

        start_time = time.time()
        response = await async_client.get("/v1/health")
        end_time = time.time()

        assert response.status_code == 200
        assert (end_time - start_time) < 1.0  # Should respond within 1 second

    async def test_health_endpoint_concurrent_requests(self, async_client: AsyncClient):
        """Test health endpoint with concurrent requests."""
        import asyncio

        async def make_request():
            return await async_client.get("/v1/health")

        # Make 10 concurrent requests
        tasks = [make_request() for _ in range(10)]
        responses = await asyncio.gather(*tasks)

        # All requests should succeed
        for response in responses:
            assert response.status_code == 200
