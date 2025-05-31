import pytest

from app.domain.v1.auth.handlers.client_find_authenticated_handler import (
    ClientFindAuthenticatedHandler,
)
from app.domain.v1.auth.requests import ClientFindAuthenticatedRequest


class TestClientFindAuthenticatedHandler:
    """Test suite for ClientFindAuthenticatedHandler."""

    @pytest.fixture
    def handler(self):
        """Create handler instance."""

        return ClientFindAuthenticatedHandler()

    @pytest.fixture
    def authenticated_request(self, test_client_model, mock_request):
        """Create ClientFindAuthenticatedRequest with authenticated client."""

        return ClientFindAuthenticatedRequest(
            trace_id="test-trace-id",
            request_id="test-request-id",
            req=mock_request,
            client=test_client_model,
        )

    @pytest.mark.asyncio
    async def test_successful_client_retrieval(
        self, handler, authenticated_request, test_client_model
    ):
        """Test successful retrieval of authenticated client."""

        # Execute handler
        response = await handler._handle_internal(authenticated_request)

        # Verify response contains client data
        assert response.data.client_id == test_client_model.client_id
        assert response.data.is_active == test_client_model.is_active
        assert response.data.created_at == test_client_model.created_at

        # Verify scopes are properly extracted
        expected_scopes = [scope.name for scope in test_client_model.scopes]
        assert response.data.scopes == expected_scopes

    @pytest.mark.asyncio
    async def test_client_with_no_scopes(self, handler, mock_request, test_timezone):
        """Test client retrieval when client has no scopes."""

        from datetime import datetime

        from prisma.models import Client

        # Create client without scopes
        client_no_scopes = Client(
            id="client-no-scopes",
            client_id="client-id-no-scopes",
            hashed_secret="<PASSWORD>",
            name="Client Without Scopes",
            is_active=True,
            scopes=[],
            created_at=datetime.now(test_timezone),
            updated_at=datetime.now(test_timezone),
        )

        request = ClientFindAuthenticatedRequest(
            trace_id="test-trace-id",
            request_id="test-request-id",
            req=mock_request,
            client=client_no_scopes,
        )

        # Execute handler
        response = await handler._handle_internal(request)

        # Verify empty scopes list
        assert response.data.scopes == []

    @pytest.mark.asyncio
    async def test_client_with_none_scopes(self, handler, mock_request, test_timezone):
        """Test client retrieval when client.scopes is None."""

        from datetime import datetime

        from prisma.models import Client

        # Create client with None scopes
        client_none_scopes = Client(
            id="client-none-scopes",
            client_id="client-id-none-scopes",
            hashed_secret="<PASSWORD>",
            name="Client With None Scopes",
            is_active=True,
            scopes=[],
            created_at=datetime.now(test_timezone),
            updated_at=datetime.now(test_timezone),
        )

        request = ClientFindAuthenticatedRequest(
            trace_id="test-trace-id",
            request_id="test-request-id",
            req=mock_request,
            client=client_none_scopes,
        )

        # Execute handler
        response = await handler._handle_internal(request)

        # Verify scopes handling when None
        assert response.data.scopes == []

    @pytest.mark.asyncio
    async def test_inactive_client_retrieval(
        self, handler, test_client_inactive, mock_request
    ):
        """Test retrieval of inactive client."""

        request = ClientFindAuthenticatedRequest(
            trace_id="test-trace-id",
            request_id="test-request-id",
            req=mock_request,
            client=test_client_inactive,
        )

        # Execute handler
        response = await handler._handle_internal(request)

        # Verify inactive client data is returned
        assert response.data.client_id == test_client_inactive.client_id
        assert response.data.is_active is False

    @pytest.mark.asyncio
    async def test_response_type_validation(self, handler, authenticated_request):
        """Test that response is of correct type."""

        from app.domain.v1.auth.responses import ClientFindAuthenticatedResponse

        # Execute handler
        response = await handler._handle_internal(authenticated_request)

        # Verify response type
        assert isinstance(response, ClientFindAuthenticatedResponse)
        assert hasattr(response.data, "client_id")
        assert hasattr(response.data, "scopes")
