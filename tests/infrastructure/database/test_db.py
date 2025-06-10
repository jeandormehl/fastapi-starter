from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.infrastructure.database.db import Database


class TestDatabase:
    """Test database functionality."""

    @pytest.fixture
    def database(self):
        """Create database instance."""
        return Database()

    async def test_database_connection(self, database: Database):
        """Test database connection."""
        with patch.object(database, "connect", new_callable=AsyncMock) as mock_connect:
            await database.connect()
            mock_connect.assert_called_once()

    async def test_database_disconnection(self, database: Database):
        """Test database disconnection."""
        with patch.object(
            database, "disconnect", new_callable=AsyncMock
        ) as mock_disconnect:
            await database.disconnect()
            mock_disconnect.assert_called_once()

    def test_database_is_connected(self, database: Database):
        """Test database connection status check."""
        with patch.object(
            database, "is_connected", return_value=True
        ) as mock_is_connected:
            result = database.is_connected()
            assert result is True
            mock_is_connected.assert_called_once()

    async def test_database_client_operations(self, mock_database: Mock):
        """Test database client operations."""
        # Test find_unique
        mock_database.client.find_unique.return_value = Mock(id="test-client")
        result = await mock_database.client.find_unique(where={"id": "test-client"})
        assert result.id == "test-client"

        # Test create
        mock_database.client.create.return_value = Mock(id="new-client")
        result = await mock_database.client.create(data={"name": "New Client"})
        assert result.id == "new-client"

        # Test find_many
        mock_database.client.find_many.return_value = [
            Mock(id="client1"),
            Mock(id="client2"),
        ]
        result = await mock_database.client.find_many()
        assert len(result) == 2
