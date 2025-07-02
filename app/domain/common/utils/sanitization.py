import re
from typing import Any, ClassVar


class DataSanitizer:
    """
    Centralized data sanitization for logs, responses, and other data structures.
    """

    SENSITIVE_PATTERNS: ClassVar = [
        # Credit card numbers
        (r'\b(?:\d{4}[-\s]?){3}\d{4}\b', '<REDACTED_CC>'),
        # Email addresses
        (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '<REDACTED_EMAIL>'),
        # Phone numbers (common formats, including international with +1)
        (
            r'\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b',
            '<REDACTED_PHONE>',
        ),
        # Social Security Numbers
        (r'\b\d{3}-\d{2}-\d{4}\b', '<REDACTED_SSN>'),
        # API Keys (general pattern: 32+ alphanumeric characters)
        (r'\b[A-Za-z0-9]{32,}\b', '<REDACTED_API_KEY>'),
        # Passwords in URLs (e.g., http://user:password@example.com)
        (r'(://[^:]+:)[^@]+(@)', r'\1<REDACTED_PASSWORD>\2'),
        # Authorization headers (e.g., "Authorization: Bearer abcdef123")
        (
            (r'(authorization["\']?\s*:\s*["\']?)[^"\']+', re.IGNORECASE),
            r'\1<REDACTED_AUTH>',
        ),
        # Bearer tokens (e.g., "Bearer eyJhbGciOiJIUzI...")
        ((r'(bearer\s+)[a-zA-Z0-9\-._~+/=]+', re.IGNORECASE), r'\1<REDACTED_TOKEN>'),
        # AWS Access Key IDs (e.g., AKIAIOSFODNN7EXAMPLE)
        (r'(A3S[A-Z0-9]|AKIA|ASIA|AROA|[A-Z0-9]{20})', '<REDACTED_AWS_KEY>'),
        # AWS Secret Access Keys (e.g., wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY)
        (r'([0-9a-zA-Z\/+]{40})', '<REDACTED_AWS_SECRET>'),
    ]

    SENSITIVE_KEYS: ClassVar = [
        'password',
        'token',
        'secret',
        'key',
        'auth',
        'credential',
        'api_key',
        'private_key',
        'access_token',
        'refresh_token',
        'client_secret',
        'pin',
        'ssn',
        'credit_card',
        'cc_number',
    ]

    REDACTION_SKIP_KEYS: ClassVar = ['auth_method', 'token_type', 'grant_type']

    @classmethod
    def _redact_string(cls, text: str) -> str:
        for pattern, replacement in cls.SENSITIVE_PATTERNS:
            if isinstance(pattern, tuple):
                actual_pattern, flags = pattern
                text = re.sub(actual_pattern, replacement, text, flags=flags)

            else:
                text = re.sub(pattern, replacement, text)
        return text

    @classmethod
    def _is_sensitive_key(cls, key: str) -> bool:
        """Checks if a key indicates sensitive data."""
        lower_key = key.lower()

        return (
            any(s_key in lower_key for s_key in cls.SENSITIVE_KEYS)
            and lower_key not in cls.REDACTION_SKIP_KEYS
        )

    @classmethod
    def sanitize(cls, data: Any, max_length: int = 10000) -> Any:
        """
        Recursively sanitizes sensitive data in strings, dictionaries, and lists.
        """
        if isinstance(data, dict):
            sanitized_dict = {}
            for key, value in data.items():
                if cls._is_sensitive_key(key):
                    if isinstance(value, dict | list | tuple):
                        sanitized_dict[key] = cls.sanitize(value, max_length)

                    elif isinstance(value, bool):
                        sanitized_dict[key] = value

                    else:
                        sanitized_dict[key] = '<REDACTED>'

                else:
                    sanitized_dict[key] = cls.sanitize(value, max_length)
            return sanitized_dict

        if isinstance(data, list):
            return [cls.sanitize(item, max_length) for item in data]

        if isinstance(data, str):
            sanitized_string = cls._redact_string(data)

            if len(sanitized_string) > max_length:
                return sanitized_string[:max_length] + '...<TRUNCATED>'

            return sanitized_string
        return data

    @classmethod
    def sanitize_headers_params(cls, headers: dict[str, Any]) -> dict[str, str]:
        """Sanitize headers and params removing sensitive info and formatting."""

        safe = {}
        for key, value in headers.items():
            safe_key = key.replace('-', '_')

            if cls._is_sensitive_key(key):
                safe[safe_key] = '<REDACTED>'

            else:
                safe[safe_key] = str(value)
        return safe
