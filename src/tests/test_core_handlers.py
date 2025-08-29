from pathlib import Path
from typing import List
import pytest
from pydantic import BaseModel

from watchdantic.core.handlers import HandlerInfo, HandlerRegistry
from watchdantic.exceptions import ConfigurationError


class TestModel(BaseModel):
    x: int


def dummy_handler(models: List[TestModel], file_path: Path) -> None:
    pass


def test_handlerinfo_validation_and_registry() -> None:
    # valid
    hi = HandlerInfo(
        handler_func=dummy_handler,
        model_class=TestModel,
        pattern="*.jsonl",
        debounce=0.0,
        continue_on_error=False,
        recursive=True,
        exclude_patterns=[],
        format_handler=None,
    )
    reg = HandlerRegistry()
    reg.register(hi)
    assert reg.get_handler_names() == ["dummy_handler"]

    # duplicate name
    with pytest.raises(ConfigurationError):
        reg.register(hi)


def test_handlerinfo_invalid_values() -> None:
    with pytest.raises(ConfigurationError):
        HandlerInfo(
            handler_func=dummy_handler,
            model_class=TestModel,
            pattern="   ",  # empty after strip
            debounce=0.0,
        )

    with pytest.raises(ConfigurationError):
        HandlerInfo(
            handler_func=dummy_handler,
            model_class=TestModel,
            pattern="*.json",
            debounce=-0.1,  # negative
        )


def test_registry_matching_and_exclusions(tmp_path: Path) -> None:
    reg = HandlerRegistry()
    hi_ok = HandlerInfo(
        handler_func=dummy_handler,
        model_class=TestModel,
        pattern="*.jsonl",
        exclude_patterns=["*/ignore/*"],
    )
    reg.register(hi_ok)

    p1 = tmp_path / "file.jsonl"
    p2 = tmp_path / "file.json"  # not matched by pattern
    p3 = tmp_path / "ignore" / "file.jsonl"  # excluded by pattern

    assert reg.get_handlers_for_path(p1) == [hi_ok]
    assert reg.get_handlers_for_path(p2) == []
    assert reg.get_handlers_for_path(p3) == []
