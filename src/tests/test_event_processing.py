from __future__ import annotations

import json
from pathlib import Path
from typing import List

import pytest
from pydantic import BaseModel

# Import the FileEventProcessor from the module we just created
from watchdantic.core.watcher import FileEventProcessor

# Light-weight stand-ins if project modules are not available in the test env
try:
    from watchdantic.core.models import WatchdanticConfig, HandlerRegistry, HandlerInfo  # type: ignore
    from watchdantic.formats.jsonlines import JsonLines  # type: ignore
    from watchdantic.formats.jsonsingle import JsonSingle  # type: ignore
except Exception:
    from watchdantic.core.watcher import WatchdanticConfig, HandlerRegistry, HandlerInfo, JsonLines, JsonSingle  # type: ignore


class TestModel(BaseModel):
    id: str
    value: int


def write_jsonl(path: Path, rows: List[dict]) -> None:
    lines = "\n".join(json.dumps(r) for r in rows)
    path.write_text(lines, encoding="utf-8")


def write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj), encoding="utf-8")


def test_process_valid_jsonl(tmp_path: Path) -> None:
    called: List[List[TestModel]] = []

    def handler(models: List[TestModel], file_path: Path) -> None:
        called.append(models)

    fp = tmp_path / "data.jsonl"
    write_jsonl(fp, [{"id": "a", "value": 1}, {"id": "b", "value": 2}])

    reg = HandlerRegistry(handlers=[HandlerInfo(handler_func=handler, model_class=TestModel, pattern=str(fp))])
    cfg = WatchdanticConfig()

    proc = FileEventProcessor(registry=reg, config=cfg)
    proc.process_file_event(fp)

    assert len(called) == 1
    assert [m.value for m in called[0]] == [1, 2]


def test_process_valid_json_single_list(tmp_path: Path) -> None:
    called: List[List[TestModel]] = []

    def handler(models: List[TestModel], file_path: Path) -> None:
        called.append(models)

    fp = tmp_path / "data.json"
    write_json(fp, [{"id": "x", "value": 10}, {"id": "y", "value": 20}])

    reg = HandlerRegistry(handlers=[HandlerInfo(handler_func=handler, model_class=TestModel, pattern=str(fp))])
    cfg = WatchdanticConfig()

    proc = FileEventProcessor(registry=reg, config=cfg)
    proc.process_file_event(fp)

    assert len(called) == 1
    assert [m.value for m in called[0]] == [10, 20]


def test_file_size_limit(tmp_path: Path) -> None:
    called: List[List[TestModel]] = []

    def handler(models: List[TestModel], file_path: Path) -> None:
        called.append(models)

    fp = tmp_path / "big.jsonl"
    fp.write_bytes(b"0" * (1024 * 1024 + 1))  # > 1MB

    reg = HandlerRegistry(handlers=[HandlerInfo(handler_func=handler, model_class=TestModel, pattern=str(fp))])
    cfg = WatchdanticConfig(max_file_size=1024 * 1024)  # 1MB

    proc = FileEventProcessor(registry=reg, config=cfg)
    proc.process_file_event(fp)

    assert called == []  # skipped due to size


def test_continue_on_error_parsing(tmp_path: Path) -> None:
    called: List[List[TestModel]] = []

    def handler(models: List[TestModel], file_path: Path) -> None:
        called.append(models)

    fp = tmp_path / "bad.jsonl"
    fp.write_text("{bad json}\n", encoding="utf-8")  # invalid JSON

    reg = HandlerRegistry(
        handlers=[HandlerInfo(handler_func=handler, model_class=TestModel, pattern=str(fp), continue_on_error=True)]
    )
    cfg = WatchdanticConfig()

    proc = FileEventProcessor(registry=reg, config=cfg)
    proc.process_file_event(fp)

    assert called == []  # parsing failed but continued


def test_multiple_handlers(tmp_path: Path) -> None:
    calls: List[str] = []

    def h1(models: List[TestModel], file_path: Path) -> None:
        calls.append("h1")  # noqa: B023

    def h2(models: List[TestModel], file_path: Path) -> None:
        calls.append("h2")  # noqa: B023

    fp = tmp_path / "data.jsonl"
    write_jsonl(fp, [{"id": "a", "value": 1}])

    reg = HandlerRegistry(
        handlers=[
            HandlerInfo(handler_func=h1, model_class=TestModel, pattern=str(fp)),
            HandlerInfo(handler_func=h2, model_class=TestModel, pattern=str(fp)),
        ]
    )
    cfg = WatchdanticConfig()

    proc = FileEventProcessor(registry=reg, config=cfg)
    proc.process_file_event(fp)

    assert calls == ["h1", "h2"]


def test_format_detection(tmp_path: Path) -> None:
    proc = FileEventProcessor(registry=HandlerRegistry(), config=WatchdanticConfig())

    assert isinstance(proc._detect_format(tmp_path / "x.jsonl"), JsonLines)
    assert isinstance(proc._detect_format(tmp_path / "x.json"), JsonSingle)
    assert isinstance(proc._detect_format(tmp_path / "x.unknown"), JsonLines)


def test_exclude_patterns_respected(tmp_path: Path) -> None:
    called: List[List[TestModel]] = []

    def handler(models: List[TestModel], file_path: Path) -> None:
        called.append(models)

    fp = tmp_path / "data.jsonl"
    write_jsonl(fp, [{"id": "a", "value": 1}])

    reg = HandlerRegistry(
        handlers=[
            HandlerInfo(
                handler_func=handler,
                model_class=TestModel,
                pattern=str(tmp_path / "*.jsonl"),
                exclude_patterns=[str(fp)],
            )
        ]
    )
    cfg = WatchdanticConfig()

    proc = FileEventProcessor(registry=reg, config=cfg)
    proc.process_file_event(fp)

    assert called == []  # excluded
