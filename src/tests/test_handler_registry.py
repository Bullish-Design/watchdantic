from __future__ import annotations

from pathlib import Path
from typing import List

import pytest
from pydantic import BaseModel

from watchdantic.core.models import HandlerInfo, HandlerRegistry
from watchdantic.exceptions import ConfigurationError


# ----- Sample model & handler used throughout tests ---------------------------------


class TestModel(BaseModel):
    id: str
    value: int


def sample_handler(models: List[BaseModel], file_path: Path) -> None:  # pragma: no cover (behavior tested via registry)
    pass


def other_handler(models: List[BaseModel], file_path: Path) -> None:  # pragma: no cover
    pass


# ----- HandlerInfo validation --------------------------------------------------------


def test_handler_info_minimal_ok() -> None:
    hi = HandlerInfo(
        handler_func=sample_handler,
        model_class=TestModel,
        pattern="*.json",
        debounce=0.0,
        continue_on_error=False,
        recursive=True,
        exclude_patterns=[],
        format_handler=None,
    )

    assert hi.handler_func is sample_handler
    assert hi.model_class is TestModel
    assert hi.pattern == "*.json"
    assert hi.debounce == 0.0
    assert hi.exclude_patterns == []


def test_handler_info_pattern_required() -> None:
    with pytest.raises(ConfigurationError):
        HandlerInfo(
            handler_func=sample_handler,
            model_class=TestModel,
            pattern="",
            debounce=0.1,
            continue_on_error=False,
            recursive=True,
            exclude_patterns=[],
            format_handler=None,
        )


def test_handler_info_debounce_nonnegative() -> None:
    with pytest.raises(ConfigurationError):
        HandlerInfo(
            handler_func=sample_handler,
            model_class=TestModel,
            pattern="*.json",
            debounce=-0.1,
            continue_on_error=False,
            recursive=True,
            exclude_patterns=[],
            format_handler=None,
        )


def test_handler_info_is_frozen() -> None:
    hi = HandlerInfo(
        handler_func=sample_handler,
        model_class=TestModel,
        pattern="*.json",
        debounce=0.0,
        continue_on_error=False,
        recursive=True,
        exclude_patterns=[],
        format_handler=None,
    )
    with pytest.raises(TypeError):
        # frozen=True -> attributes cannot be mutated
        object.__setattr__(hi, "pattern", "*.jsonl")  # type: ignore[misc]


# ----- Registry registration & conflicts --------------------------------------------


def test_registry_register_and_names() -> None:
    reg = HandlerRegistry()

    h1 = HandlerInfo(
        handler_func=sample_handler,
        model_class=TestModel,
        pattern="*.json",
        debounce=0.0,
        continue_on_error=False,
        recursive=True,
        exclude_patterns=[],
        format_handler=None,
    )

    reg.register(h1)
    assert reg.get_handler_names() == ["sample_handler"]


def test_registry_duplicate_name_raises() -> None:
    reg = HandlerRegistry()

    h1 = HandlerInfo(
        handler_func=sample_handler,
        model_class=TestModel,
        pattern="*.json",
        debounce=0.0,
        continue_on_error=False,
        recursive=True,
        exclude_patterns=[],
        format_handler=None,
    )

    h2 = HandlerInfo(
        handler_func=sample_handler,  # same function -> same name
        model_class=TestModel,
        pattern="*.jsonl",
        debounce=0.0,
        continue_on_error=False,
        recursive=True,
        exclude_patterns=[],
        format_handler=None,
    )

    reg.register(h1)
    with pytest.raises(ConfigurationError):
        reg.register(h2)


def test_registry_requires_callable() -> None:
    reg = HandlerRegistry()

    class NotCallable:  # pragma: no cover (just structure)
        __name__ = "not_callable"

    hi = HandlerInfo(
        handler_func=lambda *args, **kwargs: None,  # start with valid callable
        model_class=TestModel,
        pattern="*.json",
        debounce=0.0,
        continue_on_error=False,
        recursive=True,
        exclude_patterns=[],
        format_handler=None,
    )

    # Monkeypatch the handler to a noncallable instance after creation (to simulate misuse)
    object.__setattr__(hi, "handler_func", NotCallable())  # type: ignore[misc]
    with pytest.raises(ConfigurationError):
        reg.register(hi)


# ----- Pattern matching --------------------------------------------------------------


def test_pattern_match_simple_extension() -> None:
    reg = HandlerRegistry()

    h_json = HandlerInfo(
        handler_func=sample_handler,
        model_class=TestModel,
        pattern="*.json",
        debounce=0.0,
        continue_on_error=False,
        recursive=True,
        exclude_patterns=[],
        format_handler=None,
    )

    h_jsonl = HandlerInfo(
        handler_func=other_handler,
        model_class=TestModel,
        pattern="*.jsonl",
        debounce=0.0,
        continue_on_error=False,
        recursive=True,
        exclude_patterns=[],
        format_handler=None,
    )

    reg.register(h_json)
    reg.register(h_jsonl)

    assert reg.get_handlers_for_path(Path("test.json")) == [h_json]
    assert reg.get_handlers_for_path(Path("test.jsonl")) == [h_jsonl]
    assert reg.get_handlers_for_path(Path("test.txt")) == []


def test_pattern_match_recursive_glob() -> None:
    reg = HandlerRegistry()
    h = HandlerInfo(
        handler_func=sample_handler,
        model_class=TestModel,
        pattern="data/**/*.jsonl",
        debounce=0.0,
        continue_on_error=False,
        recursive=True,
        exclude_patterns=[],
        format_handler=None,
    )
    reg.register(h)

    assert reg.get_handlers_for_path(Path("data/subdir/file.jsonl")) == [h]
    assert reg.get_handlers_for_path(Path("data/x/y/z/a.jsonl")) == [h]
    assert reg.get_handlers_for_path(Path("data/file.json")) == []


def test_exclude_patterns_applied() -> None:
    reg = HandlerRegistry()
    h = HandlerInfo(
        handler_func=sample_handler,
        model_class=TestModel,
        pattern="*",
        debounce=0.0,
        continue_on_error=False,
        recursive=True,
        exclude_patterns=["*.tmp", "ignored/*"],
        format_handler=None,
    )
    reg.register(h)

    assert reg.get_handlers_for_path(Path("file.tmp")) == []
    assert reg.get_handlers_for_path(Path("ignored/thing.json")) == []
    assert reg.get_handlers_for_path(Path("ok.json")) == [h]


def test_multiple_handlers_can_match_same_file() -> None:
    reg = HandlerRegistry()
    h1 = HandlerInfo(
        handler_func=sample_handler,
        model_class=TestModel,
        pattern="*.json",
        debounce=0.0,
        continue_on_error=False,
        recursive=True,
        exclude_patterns=[],
        format_handler=None,
    )
    h2 = HandlerInfo(
        handler_func=other_handler,
        model_class=TestModel,
        pattern="*.*",
        debounce=0.0,
        continue_on_error=False,
        recursive=True,
        exclude_patterns=[],
        format_handler=None,
    )
    reg.register(h1)
    reg.register(h2)

    matches = reg.get_handlers_for_path(Path("test.json"))
    assert h1 in matches and h2 in matches
    assert len(matches) == 2


# ----- Clear -------------------------------------------------------------------------


def test_registry_clear() -> None:
    reg = HandlerRegistry()
    h = HandlerInfo(
        handler_func=sample_handler,
        model_class=TestModel,
        pattern="*.json",
        debounce=0.0,
        continue_on_error=False,
        recursive=True,
        exclude_patterns=[],
        format_handler=None,
    )
    reg.register(h)
    assert reg.get_handler_names() == ["sample_handler"]
    reg.clear()
    assert reg.get_handler_names() == []
