"""Watchdantic exception hierarchy."""

from __future__ import annotations

from typing import Any

__all__ = [
    "WatchdanticError",
    "ConfigurationError",
    "ActionError",
]


class WatchdanticError(Exception):
    """Base exception for all Watchdantic-specific errors."""

    def __init__(self, message: str | None = None, *args: Any) -> None:
        super().__init__(message, *args)


class ConfigurationError(WatchdanticError):
    """Raised when configuration is invalid (bad TOML, missing refs, etc.)."""

    def __init__(self, message: str | None = None, *args: Any) -> None:
        super().__init__(message, *args)


class ActionError(WatchdanticError):
    """Raised when an action execution fails."""

    def __init__(self, message: str | None = None, *args: Any) -> None:
        super().__init__(message, *args)
