"""Numeric Utilities Module"""

from typing import Any


class IntUtils:
    @staticmethod
    def to_int(value: Any, default: int = 0) -> int:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default
