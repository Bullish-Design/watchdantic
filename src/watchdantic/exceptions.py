# src/watchdantic/exceptions.py
from __future__ import annotations

"""
Watchdantic exception hierarchy.

This module defines the small, focused set of exceptions that are specific to
Watchdantic's domain. Validation errors originating from Pydantic are *not*
wrapped and should be allowed to bubble up naturally to preserve their rich
diagnostic information.
"""

from typing import Any

__all__ = [
    "WatchdanticError",
    "FileFormatError",
    "ConfigurationError",
]


class WatchdanticError(Exception):
    """
    Base exception for all Watchdantic-specific errors.

    Use this as the common ancestor so library consumers can catch a single
    exception type for any Watchdantic-originating problem (excluding Pydantic
    validation issues, which are intentionally not wrapped).
    """

    def __init__(self, message: str | None = None, *args: Any) -> None:
        # Maintain standard Exception semantics: if message is None and args
        # contains items, defer to Exception's formatting; otherwise keep simple.
        super().__init__(message, *args)


class FileFormatError(WatchdanticError):
    """
    Raised when file parsing or format detection fails.

    Typical scenarios include:
    - Unsupported file extension or format auto-detection failure.
    - Corrupt or malformed content in a supported format.
    - I/O succeeded, but the content could not be parsed into models.
    """

    def __init__(self, message: str | None = None, *args: Any) -> None:
        super().__init__(message, *args)


class ConfigurationError(WatchdanticError):
    """
    Raised when Watchdantic configuration is invalid.

    Examples:
    - Invalid debounce intervals or file size limits.
    - Conflicting handler registrations or invalid handler signatures.
    - Missing required configuration values.
    """

    def __init__(self, message: str | None = None, *args: Any) -> None:
        super().__init__(message, *args)
