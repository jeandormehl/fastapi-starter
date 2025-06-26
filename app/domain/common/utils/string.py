"""String Utilities Module
Provides a collection of helper functions for common string operations.
Uses only the standard Python library.
"""

import re
import unicodedata


class StringUtils:
    """Collection of static string utility methods."""

    _NON_ALNUM_RE = re.compile(r'[^a-zA-Z0-9]+')
    _SNAKE_CASE_RE = re.compile(r'(?<!^)(?=[A-Z])')

    # ---------- Normalization ----------
    @staticmethod
    def normalize_whitespace(text: str) -> str:
        """Collapse consecutive whitespace in *text* to single spaces and trim ends."""
        return ' '.join(text.split())

    @staticmethod
    def strip_accents(text: str) -> str:
        """Remove diacritical marks (accents) from characters in *text*."""
        normalized = unicodedata.normalize('NFD', text)
        return ''.join(ch for ch in normalized if unicodedata.category(ch) != 'Mn')

    # ---------- Case Conversion ----------
    @staticmethod
    def to_snake(text: str) -> str:
        """Convert *text* from camelCase / PascalCase to snake_case."""
        text = StringUtils._SNAKE_CASE_RE.sub('_', text).lower()
        return StringUtils._NON_ALNUM_RE.sub('_', text).strip('_')

    @staticmethod
    def to_camel(text: str) -> str:
        """Convert *text* from snake_case / kebab-case to camelCase."""
        parts = re.split(r'[_\-]', text)
        return parts[0].lower() + ''.join(word.title() for word in parts[1:])

    @staticmethod
    def to_pascal(text: str) -> str:
        """Convert *text* from snake_case / kebab-case / camelCase to PascalCase."""
        camel = StringUtils.to_camel(text)
        return camel[:1].upper() + camel[1:]

    # ---------- Validation ----------
    EMAIL_RE = re.compile(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')
    URL_RE = re.compile(r'^(https?|ftp)://[^\"]+$')
    PHONE_RE = re.compile(r'^\+?[0-9 .()-]{7,}$')

    @staticmethod
    def is_email(text: str) -> bool:
        return bool(StringUtils.EMAIL_RE.match(text))

    @staticmethod
    def is_url(text: str) -> bool:
        return bool(StringUtils.URL_RE.match(text))

    @staticmethod
    def is_phone(text: str) -> bool:
        return bool(StringUtils.PHONE_RE.match(text))

    # ---------- Generation ----------
    @staticmethod
    def slugify(text: str, max_length: int | None = 80) -> str:
        """Generate URL slug from *text* limited to *max_length*."""
        text = StringUtils.strip_accents(text.lower())
        text = StringUtils._NON_ALNUM_RE.sub('-', text)
        text = re.sub(r'-{2,}', '-', text).strip('-')
        if max_length:
            text = text[:max_length].rstrip('-')
        return text

    # ---------- Masking ----------
    @staticmethod
    def mask(text: str, visible: int = 4, char: str = '*') -> str:
        """Mask sensitive *text* leaving *visible* chars at the end."""
        if visible >= len(text):
            return text
        return char * (len(text) - visible) + text[-visible:]

    # ---------- Splitting ----------
    @staticmethod
    def chunk(text: str, size: int) -> list[str]:
        """Split *text* into chunks of *size* characters."""
        return [text[i : i + size] for i in range(0, len(text), size)]
