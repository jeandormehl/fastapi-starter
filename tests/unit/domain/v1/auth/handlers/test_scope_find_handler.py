import pytest
from prisma.models import Scope

from app.core.errors.errors import DatabaseError
from app.domain.v1.auth.handlers.scope_find_handler import ScopeFindHandler
from app.domain.v1.auth.requests import ScopeFindRequest


class TestScopeFindHandler:
    """Test suite for ScopeFindHandler."""

    @pytest.fixture
    def handler(self):
        """Create handler instance."""

        return ScopeFindHandler()

    @pytest.fixture
    def scope_find_request(self, mock_request):
        """Create ScopeFindRequest."""

        return ScopeFindRequest(
            trace_id="test-trace-id", request_id="test-request-id", req=mock_request
        )

    @pytest.fixture
    def database_scopes(self):
        """Create mock database scopes."""

        return [
            Scope(id="scope-1", name="read", description="Read access to resources"),
            Scope(id="scope-2", name="write", description="Write access to resources"),
            Scope(id="scope-3", name="admin", description="Administrative access"),
        ]

    @pytest.mark.asyncio
    async def test_successful_scope_retrieval(
        self, handler, scope_find_request, database_scopes, mock_database
    ):
        """Test successful retrieval of all scopes."""

        # Mock database response
        mock_database.scope.find_many.return_value = database_scopes

        # Execute handler
        response = await handler._handle_internal(scope_find_request)

        # Verify database query
        mock_database.scope.find_many.assert_called_once_with()

        # Verify response
        assert len(response.data) == 3

        # Verify first scope
        assert response.data[0].name == "read"
        assert response.data[0].description == "Read access to resources"

        # Verify second scope
        assert response.data[1].name == "write"
        assert response.data[1].description == "Write access to resources"

        # Verify third scope
        assert response.data[2].name == "admin"
        assert response.data[2].description == "Administrative access"

    @pytest.mark.asyncio
    async def test_empty_scope_list(self, handler, scope_find_request, mock_database):
        """Test handling of empty scope list from database."""

        # Mock empty database response
        mock_database.scope.find_many.return_value = []

        # Execute handler
        response = await handler._handle_internal(scope_find_request)

        # Verify empty response
        assert response.data == []

    @pytest.mark.asyncio
    async def test_single_scope(self, handler, scope_find_request, mock_database):
        """Test handling of single scope from database."""

        # Mock single scope response
        single_scope = [Scope(id="scope-1", name="read", description="Read access")]
        mock_database.scope.find_many.return_value = single_scope

        # Execute handler
        response = await handler._handle_internal(scope_find_request)

        # Verify single scope response
        assert len(response.data) == 1
        assert response.data[0].name == "read"
        assert response.data[0].description == "Read access"

    @pytest.mark.asyncio
    async def test_database_exception_handling(
        self, handler, scope_find_request, mock_database
    ):
        """Test exception handling during database query."""

        # Mock database exception
        mock_database.scope.find_many.side_effect = DatabaseError(
            "Database connection error"
        )

        # Execute and expect exception propagation
        with pytest.raises(DatabaseError) as exc_info:
            await handler._handle_internal(scope_find_request)

        assert "Database connection error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_scope_data_transformation(
        self, handler, scope_find_request, mock_database
    ):
        """Test that scope data is properly transformed to ScopeOut."""

        from app.domain.v1.auth.schemas import ScopeOut

        # Mock database response with comprehensive scope data
        comprehensive_scope = [
            Scope(
                id="scope-1",
                name="comprehensive",
                description="A comprehensive scope for testing",
            )
        ]
        mock_database.scope.find_many.return_value = comprehensive_scope

        # Execute handler
        response = await handler._handle_internal(scope_find_request)

        # Verify response data type and content
        assert len(response.data) == 1
        assert isinstance(response.data[0], ScopeOut)
        assert response.data[0].name == "comprehensive"
        assert response.data[0].description == "A comprehensive scope for testing"

    @pytest.mark.asyncio
    async def test_scope_with_special_characters(
        self, handler, scope_find_request, mock_database
    ):
        """Test handling of scopes with special characters."""

        # Mock scope with special characters
        special_scope = [
            Scope(
                id="scope-1",
                name="api:read-write",
                description="API access with read/write permissions & special chars",
            )
        ]
        mock_database.scope.find_many.return_value = special_scope

        # Execute handler
        response = await handler._handle_internal(scope_find_request)

        # Verify special characters are preserved
        assert response.data[0].name == "api:read-write"
        assert "read/write permissions & special chars" in response.data[0].description

    @pytest.mark.asyncio
    async def test_request_parameter_ignored(
        self, handler, scope_find_request, database_scopes, mock_database
    ):
        """Test that request parameter is properly ignored in handler."""

        # Mock database response
        mock_database.scope.find_many.return_value = database_scopes

        # Execute handler - request parameter should be ignored
        response = await handler._handle_internal(scope_find_request)

        # Verify database call doesn't use request data
        mock_database.scope.find_many.assert_called_once_with()

        # Verify response is still correct
        assert len(response.data) == 3
