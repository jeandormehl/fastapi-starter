import pytest

from app.domain.v1.auth.scopes import SCOPE_DESCRIPTIONS, AuthScope


class TestAuthScope:
    """Test the AuthScope enumeration."""

    def test_auth_scope_values(self):
        """Test that auth scope values are correct."""

        assert AuthScope.READ == "read"
        assert AuthScope.WRITE == "write"
        assert AuthScope.ADMIN == "admin"

    def test_auth_scope_string_inheritance(self):
        """Test that AuthScope inherits from str."""

        assert isinstance(AuthScope.READ, str)
        assert isinstance(AuthScope.WRITE, str)
        assert isinstance(AuthScope.ADMIN, str)

    def test_auth_scope_comparison(self):
        """Test scope comparison operations."""

        assert AuthScope.READ == "read"
        assert AuthScope.WRITE != "read"
        assert AuthScope.ADMIN == "admin"

    def test_auth_scope_in_collection(self):
        """Test scope membership in collections."""

        scopes = [AuthScope.READ, AuthScope.WRITE]
        assert AuthScope.READ in scopes
        assert AuthScope.ADMIN not in scopes

        scope_set = {AuthScope.READ, AuthScope.WRITE, AuthScope.ADMIN}
        assert len(scope_set) == 3
        assert AuthScope.ADMIN in scope_set

    def test_auth_scope_case_sensitivity(self):
        """Test that scopes are casesensitive."""

        assert AuthScope.READ != "READ"
        assert AuthScope.WRITE != "Write"
        assert AuthScope.ADMIN != "ADMIN"

    def test_auth_scope_iteration(self):
        """Test iteration over AuthScope enum."""

        all_scopes = list(AuthScope)
        assert len(all_scopes) == 3
        assert AuthScope.READ in all_scopes
        assert AuthScope.WRITE in all_scopes
        assert AuthScope.ADMIN in all_scopes

    def test_auth_scope_membership(self):
        """Test membership testing with AuthScope."""

        scope_list = ["read", "write"]
        assert AuthScope.READ in scope_list
        assert AuthScope.ADMIN not in scope_list

    @pytest.mark.parametrize(
        ("scope", "expected"),
        [
            (AuthScope.READ, "read"),
            (AuthScope.WRITE, "write"),
            (AuthScope.ADMIN, "admin"),
        ],
    )
    def test_auth_scope_parametrized_values(self, scope, expected):
        """Test scope values using parametrization."""

        assert scope == expected
        assert scope.value == expected


class TestScopeDescriptions:
    """Test the SCOPE_DESCRIPTIONS dictionary."""

    def test_scope_descriptions_completeness(self):
        """Test that all scopes have descriptions."""

        for scope in AuthScope:
            assert scope in SCOPE_DESCRIPTIONS
            assert SCOPE_DESCRIPTIONS[scope] is not None
            assert len(SCOPE_DESCRIPTIONS[scope]) > 0

    def test_scope_descriptions_content(self):
        """Test the content of scope descriptions."""

        assert SCOPE_DESCRIPTIONS[AuthScope.READ] == "read access to resources"
        assert SCOPE_DESCRIPTIONS[AuthScope.WRITE] == "write access to resources"
        assert SCOPE_DESCRIPTIONS[AuthScope.ADMIN] == "administrative access"

    def test_scope_descriptions_types(self):
        """Test that all descriptions are strings."""

        for scope, description in SCOPE_DESCRIPTIONS.items():
            assert isinstance(scope, AuthScope)
            assert isinstance(description, str)
            assert len(description.strip()) > 0

    def test_scope_descriptions_no_extra_keys(self):
        """Test that SCOPE_DESCRIPTIONS contains no extra keys."""

        expected_scopes = set(AuthScope)
        actual_scopes = set(SCOPE_DESCRIPTIONS.keys())
        assert expected_scopes == actual_scopes

    def test_scope_descriptions_accessibility(self):
        """Test that descriptions are accessible by scope values."""

        assert SCOPE_DESCRIPTIONS[AuthScope.READ] == "read access to resources"
        assert SCOPE_DESCRIPTIONS[AuthScope.WRITE] == "write access to resources"
        assert SCOPE_DESCRIPTIONS[AuthScope.ADMIN] == "administrative access"

    def test_scope_descriptions_format(self):
        """Test that descriptions follow consistent format."""

        for description in SCOPE_DESCRIPTIONS.values():
            # All descriptions should be lowercase
            assert description == description.lower()
            # All descriptions should end with "access" or "access to resources"
            assert "access" in description

    @pytest.mark.parametrize(
        ("scope", "expected_desc"),
        [
            (AuthScope.READ, "read access to resources"),
            (AuthScope.WRITE, "write access to resources"),
            (AuthScope.ADMIN, "administrative access"),
        ],
    )
    def test_scope_descriptions_parametrized(self, scope, expected_desc):
        """Test scope descriptions using parametrization."""

        assert SCOPE_DESCRIPTIONS[scope] == expected_desc

    def test_scope_descriptions_immutability(self):
        """Test that scope descriptions dictionary behaves correctly."""

        # Test that we can read from it
        read_desc = SCOPE_DESCRIPTIONS[AuthScope.READ]
        assert read_desc == "read access to resources"

        # Test that keys and values work as expected
        assert len(SCOPE_DESCRIPTIONS) == 3
        assert list(SCOPE_DESCRIPTIONS.keys()) == [
            AuthScope.READ,
            AuthScope.WRITE,
            AuthScope.ADMIN,
        ]
