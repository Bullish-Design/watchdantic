# tests/test_exceptions.py
from __future__ import annotations

import importlib
from typing import Type

import pytest
from pydantic import BaseModel, ValidationError

from watchdantic.exceptions import (
    WatchdanticError,
    FileFormatError,
    ConfigurationError,
)


def test_inheritance_hierarchy() -> None:
    assert issubclass(WatchdanticError, Exception)
    assert issubclass(FileFormatError, WatchdanticError)
    assert issubclass(ConfigurationError, WatchdanticError)


def test_raise_and_catch_specific() -> None:
    with pytest.raises(FileFormatError) as ei:
        raise FileFormatError("bad jsonl")
    assert "bad jsonl" in str(ei.value)

    with pytest.raises(ConfigurationError) as ei2:
        raise ConfigurationError("invalid debounce")
    assert "invalid debounce" in str(ei2.value)


def test_catch_generically() -> None:
    # Generic catch-all for Watchdantic-specific errors.
    try:
        raise FileFormatError("parse failed")
    except WatchdanticError as e:
        assert isinstance(e, FileFormatError)
        assert "parse failed" in str(e)
    else:
        pytest.fail("WatchdanticError was not caught generically")


def test_messages_preserved() -> None:
    msg = "something went wrong"
    e = WatchdanticError(msg)
    assert str(e) == msg

    msg2 = "format broke"
    e2 = FileFormatError(msg2)
    assert str(e2) == msg2


def test_import_paths_work() -> None:
    mod = importlib.import_module("watchdantic.exceptions")
    # Attributes exist and are classes
    for name in ("WatchdanticError", "FileFormatError", "ConfigurationError"):
        assert hasattr(mod, name)
        attr = getattr(mod, name)
        assert isinstance(attr, type)
        assert issubclass(attr, Exception)


def test_pydantic_validation_error_not_wrapped() -> None:
    class Demo(BaseModel):
        x: int

    # Intentionally cause a pydantic.ValidationError
    with pytest.raises(ValidationError) as ei:
        Demo(x="not-an-int")  # type: ignore[arg-type]

    err = ei.value
    # Ensure we did not wrap it in our hierarchy
    assert isinstance(err, ValidationError)
    assert not isinstance(err, WatchdanticError)
    assert "x" in str(err)
