from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any, Dict

import pytest
from pydantic import BaseModel, ValidationError

# Import from project
from watchdantic.core.models import WatchdanticLogger, WatchdanticConfig
from watchdantic.exceptions import FileFormatError


class DummyModel(BaseModel):
    a: int


def _mk_config(tmp_path: Path, enable: bool, level: str = "INFO", to_file: bool = True) -> WatchdanticConfig:
    # WatchdanticConfig is expected to already exist with fields used below.
    return WatchdanticConfig(
        enable_logging=enable,
        log_level=level,
        log_file=(tmp_path / "watchdantic.jsonl") if to_file else None,
    )


def _read_json_lines(path: Path) -> list[Dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_disabled_does_not_write(tmp_path: Path) -> None:
    cfg = _mk_config(tmp_path, enable=False, to_file=True)
    logger = WatchdanticLogger(config=cfg)
    # Intentionally try to log
    logger.log_event("INFO", "Should not appear")
    p = cfg.log_file
    assert p is not None
    assert not p.exists() or p.read_text(encoding="utf-8").strip() == ""


def test_file_output_and_json_shape(tmp_path: Path) -> None:
    cfg = _mk_config(tmp_path, enable=True, to_file=True)
    wl = WatchdanticLogger(config=cfg)
    wl.log_file_processed(tmp_path / "x.jsonl", "process_logs", 3)

    assert cfg.log_file is not None
    lines = _read_json_lines(cfg.log_file)
    assert len(lines) == 1
    row = lines[0]
    # Mandatory fields
    assert {"timestamp", "level", "message"} <= row.keys()
    # Structured fields
    assert row["file_path"].endswith("x.jsonl")
    assert row["handler_name"] == "process_logs"
    assert row["model_count"] == 3
    assert row["level"] == "INFO"
    assert "T" in row["timestamp"] and row["timestamp"].endswith("Z")


def test_console_output_when_no_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cfg = _mk_config(tmp_path, enable=True, to_file=False)
    wl = WatchdanticLogger(config=cfg)
    wl.log_event("INFO", "hello console", ctx=True)

    out = capsys.readouterr().out.strip()
    assert out, "Expected something printed to stdout"
    doc = json.loads(out)
    assert doc["message"] == "hello console"
    assert doc["ctx"] is True


def test_level_filtering_respected(tmp_path: Path) -> None:
    cfg = _mk_config(tmp_path, enable=True, level="ERROR", to_file=True)
    wl = WatchdanticLogger(config=cfg)

    # Below level -> should not write
    wl.log_event("INFO", "too low")
    # At/above level -> should write
    wl.log_event("ERROR", "important")

    lines = _read_json_lines(cfg.log_file) if cfg.log_file and cfg.log_file.exists() else []
    assert len(lines) == 1
    assert lines[0]["message"] == "important"
    assert lines[0]["level"] == "ERROR"


def test_validation_and_format_errors_are_structured(tmp_path: Path) -> None:
    cfg = _mk_config(tmp_path, enable=True, to_file=True)
    wl = WatchdanticLogger(config=cfg)

    # Build a ValidationError using Pydantic
    try:
        DummyModel(a="bad")  # type: ignore[arg-type]
    except ValidationError as ve:
        wl.log_validation_error(tmp_path / "bad.jsonl", ve)

    wl.log_format_error(tmp_path / "bad.json", FileFormatError("broken json"))

    lines = _read_json_lines(cfg.log_file)
    # two lines appended
    assert len(lines) == 2
    v_doc, f_doc = lines

    assert v_doc["level"] == "ERROR" and f_doc["level"] == "ERROR"
    assert v_doc["file_path"].endswith("bad.jsonl")
    assert f_doc["file_path"].endswith("bad.json")
    assert v_doc["error_type"] == "ValidationError"
    assert isinstance(v_doc["errors"], list)
    assert f_doc["error_type"] == "FileFormatError"
    assert "broken json" in f_doc["details"]
