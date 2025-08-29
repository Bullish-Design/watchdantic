# tests/test_decorator.py
from __future__ import annotations

from pathlib import Path
from typing import List

import pytest
from pydantic import BaseModel

from watchdantic.core.watcher import WatchdanticCore
from watchdantic.exceptions import ConfigurationError
from watchdantic.formats.jsonlines import JsonLines
from watchdantic.formats.jsonsingle import JsonSingle


class _TModel(BaseModel):
    id: str


def _mk_core() -> WatchdanticCore:
    return WatchdanticCore()


def test_valid_decorator_registers_handler(tmp_path: Path) -> None:
    core = _mk_core()

    @core.triggers_on(_TModel, "*.json")
    def handler(models: List[_TModel], file_path: Path) -> None:
        pass

    # Ensure registered - handlers is a dict, not a list
    regs = core.registry.handlers
    assert len(regs) == 1
    hi = list(regs.values())[0]  # Get first handler from dict
    assert hi.model_class is _TModel
    assert hi.pattern == "*.json"
    # autodetect for *.json should be JsonSingle
    assert isinstance(hi.format_handler, JsonSingle)


def test_signature_validation_models_param_type() -> None:
    core = _mk_core()

    with pytest.raises(ConfigurationError):

        @core.triggers_on(_TModel, "*.json")
        def bad_a(models: _TModel, file_path: Path) -> None:  # type: ignore[valid-type]
            pass


def test_signature_validation_missing_annotations() -> None:
    core = _mk_core()

    with pytest.raises(ConfigurationError):

        @core.triggers_on(_TModel, "*.json")
        def bad_b(models, file_path):  # type: ignore[no-untyped-def]
            pass


def test_second_param_must_be_path() -> None:
    core = _mk_core()

    with pytest.raises(ConfigurationError):

        @core.triggers_on(_TModel, "*.json")
        def bad_c(models: List[_TModel], file_path: str) -> None:  # type: ignore[override]
            pass


def test_return_annotation_must_be_none() -> None:
    core = _mk_core()

    with pytest.raises(ConfigurationError):

        @core.triggers_on(_TModel, "*.json")
        def bad_d(models: List[_TModel], file_path: Path) -> int:  # type: ignore[override]
            return 0


def test_parameter_validation_errors() -> None:
    core = _mk_core()

    # empty pattern
    with pytest.raises(ConfigurationError):

        @core.triggers_on(_TModel, "")
        def _h1(models: List[_TModel], file_path: Path) -> None:
            pass

    # model_class not BaseModel subclass
    with pytest.raises(ConfigurationError):
        core.triggers_on(object, "*.json")  # type: ignore[arg-type]

    # negative debounce
    with pytest.raises(ConfigurationError):
        core.triggers_on(_TModel, "*.json", debounce=-1.0)

    # exclude_patterns must be list[str]
    with pytest.raises(ConfigurationError):
        core.triggers_on(_TModel, "*.json", exclude_patterns=123)  # type: ignore[arg-type]

    # format must be FileFormatBase (pass a wrong object)
    with pytest.raises(ConfigurationError):
        core.triggers_on(_TModel, "*.json", format=object())  # type: ignore[arg-type]


def test_multiple_handlers_register_independently() -> None:
    core = _mk_core()

    @core.triggers_on(_TModel, "*.json")
    def a(models: List[_TModel], file_path: Path) -> None:
        pass

    @core.triggers_on(_TModel, "*.jsonl")
    def b(models: List[_TModel], file_path: Path) -> None:
        pass

    assert len(core.registry.handlers) == 2
    handlers_list = list(core.registry.handlers.values())
    patterns = {h.pattern for h in handlers_list}
    assert patterns == {"*.json", "*.jsonl"}


def test_format_autodetection() -> None:
    core = _mk_core()

    @core.triggers_on(_TModel, "*.jsonl")
    def h1(models: List[_TModel], file_path: Path) -> None:
        pass

    @core.triggers_on(_TModel, "*.json")
    def h2(models: List[_TModel], file_path: Path) -> None:
        pass

    handlers_list = list(core.registry.handlers.values())
    # Find handlers by pattern since dict order isn't guaranteed
    jsonl_handler = next(h for h in handlers_list if h.pattern == "*.jsonl")
    json_handler = next(h for h in handlers_list if h.pattern == "*.json")

    assert isinstance(jsonl_handler.format_handler, JsonLines)
    assert isinstance(json_handler.format_handler, JsonSingle)


def test_explicit_format_override() -> None:
    core = _mk_core()

    # Pattern suggests JsonSingle, but we explicitly pass JsonLines()
    @core.triggers_on(_TModel, "*.json", format=JsonLines())
    def h(models: List[_TModel], file_path: Path) -> None:
        pass

    handlers_list = list(core.registry.handlers.values())
    hi = handlers_list[0]
    assert isinstance(hi.format_handler, JsonLines)
