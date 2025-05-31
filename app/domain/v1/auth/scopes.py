from enum import Enum


class AuthScope(str, Enum):
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


SCOPE_DESCRIPTIONS = {
    AuthScope.READ: "read access to resources",
    AuthScope.WRITE: "write access to resources",
    AuthScope.ADMIN: "administrative access",
}
