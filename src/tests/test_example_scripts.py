# Step 16: Example Script Validation
# --------------------------------------------------------------------------------------
# These tests validate the full Watchdantic implementation using patterns from the three
# provided example scripts:
#   1) basic_usage_script.py           -> Log processing with error detection
#   2) etl_pipeline_script.py          -> Multi-stage data transformation
#   3) config_hotreload_script.py      -> Configuration file monitoring + hot-reload
#
# The tests avoid "run forever" behavior by using short-lived watchers and sleeps.
# They rely on Watchdantic's public API:
#   - Watchdantic(...)
#   - .triggers_on(Model, "glob/pattern")
#   - .start(root_path)
#   - .stop()
#
# Each test creates a temp directory and files within it, writes data, and then waits
# briefly for the watcher to process events. Handlers append to in-memory lists so the
# test can assert on observed behavior.
# --------------------------------------------------------------------------------------

from __future__ import annotations

import json
import time
import logging
from pathlib import Path
from typing import List

import pytest
from pydantic import BaseModel

# Import from the library under test
from watchdantic import Watchdantic, WatchdanticConfig


# Configure verbose logging for easier debugging of failures
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s [test] %(message)s")
logger = logging.getLogger(__name__)


# --- Helpers ---------------------------------------------------------------------------


def _sleep_brief(seconds: float = 0.5) -> None:
    """Small helper to sleep with a debug log for deterministic tests."""
    logger.debug("Sleeping for %.2fs to allow event processing...", seconds)
    time.sleep(seconds)


# --- Models for tests (mirroring example scripts) --------------------------------------


class LogEntry(BaseModel):
    timestamp: str
    level: str
    message: str


class RawRecord(BaseModel):
    id: int
    value: int


class EnrichedRecord(BaseModel):
    id: int
    value: int
    doubled: int


class AppConfig(BaseModel):
    name: str
    enabled: bool
    retries: int


# --- Tests -----------------------------------------------------------------------------


def test_basic_usage_script_pattern(tmp_path: Path) -> None:
    """Validate the basic log processing example: watch logs/*.jsonl and collect ERRORs."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "events.jsonl"

    errors: List[str] = []

    watcher = Watchdantic(WatchdanticConfig(debounce_seconds=0.1))

    @watcher.triggers_on(LogEntry, "logs/*.jsonl")
    def process_logs(models: List[LogEntry], file_path: Path) -> None:  # noqa: F811
        logging.getLogger("test").debug("process_logs called with %d models from %s", len(models), file_path)
        for entry in models:
            if entry.level.upper() == "ERROR":
                errors.append(entry.message)

    # Start watcher and create data
    watcher.start(tmp_path)

    try:
        # Write multiple lines (JSONL)
        lines = [
            json.dumps({"timestamp": "2025-08-28T12:00:00Z", "level": "INFO", "message": "started"}),
            json.dumps({"timestamp": "2025-08-28T12:01:00Z", "level": "ERROR", "message": "boom 1"}),
            json.dumps({"timestamp": "2025-08-28T12:02:00Z", "level": "WARN", "message": "degraded"}),
            json.dumps({"timestamp": "2025-08-28T12:03:00Z", "level": "ERROR", "message": "boom 2"}),
        ]
        log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        _sleep_brief(0.6)  # allow debounce + processing

        assert "boom 1" in errors and "boom 2" in errors
        assert len(errors) == 2
    finally:
        watcher.stop()


def test_etl_pipeline_script_pattern(tmp_path: Path) -> None:
    """Validate a multi-stage ETL pipeline:
    - Stage A: ingest raw/*.jsonl -> RawRecord
    - Stage B: transform to enriched/*.jsonl -> EnrichedRecord (write output)
    - Stage C: summary generation based on enriched output
    """
    raw_dir = tmp_path / "raw"
    enriched_dir = tmp_path / "enriched"
    summary_dir = tmp_path / "summary"
    for d in (raw_dir, enriched_dir, summary_dir):
        d.mkdir(parents=True, exist_ok=True)

    enriched_events: List[EnrichedRecord] = []
    summaries: List[dict] = []

    cfg = WatchdanticConfig(debounce_seconds=0.1)
    watcher = Watchdantic(cfg)

    @watcher.triggers_on(RawRecord, "raw/*.jsonl")
    def transform_stage(models: List[RawRecord], file_path: Path) -> None:  # noqa: F811
        logging.getLogger("test").debug("transform_stage received %d models from %s", len(models), file_path)
        # Transform: double the values and write to enriched/*.jsonl
        out_path = enriched_dir / file_path.name
        with out_path.open("w", encoding="utf-8") as f:
            for m in models:
                out = {"id": m.id, "value": m.value, "doubled": m.value * 2}
                f.write(json.dumps(out) + "\n")

    @watcher.triggers_on(EnrichedRecord, "enriched/*.jsonl")
    def summary_stage(models: List[EnrichedRecord], file_path: Path) -> None:  # noqa: F811
        logging.getLogger("test").debug("summary_stage received %d models from %s", len(models), file_path)
        enriched_events.extend(models)
        # Create a trivial summary
        total = sum(m.doubled for m in models)
        count = len(models)
        summary = {"file": file_path.name, "count": count, "total": total}
        summaries.append(summary)
        # Write a summary.json for completeness
        (summary_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")

    watcher.start(tmp_path)
    try:
        # Seed raw input
        raw_file = raw_dir / "records.jsonl"
        with raw_file.open("w", encoding="utf-8") as f:
            for i in range(5):
                f.write(json.dumps({"id": i, "value": i + 1}) + "\n")

        _sleep_brief(1.0)  # allow both stages to execute

        # Validate enriched results observed
        assert len(enriched_events) == 5
        assert any(m.doubled == 2 for m in enriched_events)  # first
        assert any(m.doubled == 10 for m in enriched_events)  # last

        # Validate summary
        assert summaries, "Expected at least one summary object"
        s = summaries[-1]
        assert s["count"] == 5
        assert s["total"] == sum((i + 1) * 2 for i in range(5))
        # Check file presence
        assert (summary_dir / "summary.json").exists()
    finally:
        watcher.stop()


def test_config_hotreload_script_pattern(tmp_path: Path) -> None:
    """Validate JSON file monitoring for configuration + hot-reload semantics with quick debounce."""
    cfg_path = tmp_path / "config.json"
    states: List[AppConfig] = []

    watcher = Watchdantic(WatchdanticConfig(debounce_seconds=0.1))

    @watcher.triggers_on(AppConfig, "config.json")
    def apply_config(models: List[AppConfig], file_path: Path) -> None:  # noqa: F811
        logging.getLogger("test").debug("apply_config received %d models from %s", len(models), file_path)
        # JsonSingle should yield a single model in a list
        assert len(models) == 1
        states.append(models[0])

    watcher.start(tmp_path)
    try:
        # Initial write
        cfg_path.write_text(json.dumps({"name": "svc", "enabled": False, "retries": 1}), encoding="utf-8")
        _sleep_brief(0.5)
        assert states and states[-1].enabled is False and states[-1].retries == 1

        # Hot reload update
        cfg_path.write_text(json.dumps({"name": "svc", "enabled": True, "retries": 3}), encoding="utf-8")
        _sleep_brief(0.6)
        assert states[-1].enabled is True and states[-1].retries == 3
    finally:
        watcher.stop()
