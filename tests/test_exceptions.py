"""Tests for exception hierarchy."""

from __future__ import annotations

from watchdantic.exceptions import ActionError, ConfigurationError, WatchdanticError


class TestExceptionHierarchy:
    def test_base_exception(self):
        exc = WatchdanticError("test")
        assert str(exc) == "test"
        assert isinstance(exc, Exception)

    def test_configuration_error(self):
        exc = ConfigurationError("bad config")
        assert isinstance(exc, WatchdanticError)
        assert isinstance(exc, Exception)

    def test_action_error(self):
        exc = ActionError("action failed")
        assert isinstance(exc, WatchdanticError)

    def test_catch_base(self):
        try:
            raise ConfigurationError("test")
        except WatchdanticError:
            pass  # Should be caught by base class
