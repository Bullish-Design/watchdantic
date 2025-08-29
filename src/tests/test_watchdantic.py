from __future__ import annotations

import json
import time
from pathlib import Path
from typing import List

from pydantic import BaseModel

from watchdantic import Watchdantic, WatchdanticConfig


# Ignore the test model (pytest is picking it up as a test case):
import warnings

warnings.filterwarnings("ignore", message="cannot collect test class 'TestModel' because it has a __init__ constructor")


class TestModel(BaseModel):
    x: int


def _wait_until(predicate, timeout=5.0, interval=0.05):
    start = time.time()
    while time.time() - start < timeout:
        if predicate():
            return True
        time.sleep(interval)
    return False


def test_start_stop_lifecycle(tmp_path: Path) -> None:
    watcher = Watchdantic(WatchdanticConfig())
    watcher.start(tmp_path)
    watcher.stop()


def test_handler_receives_jsonl(tmp_path: Path) -> None:
    events: List[List[TestModel]] = []

    # Use zero debounce time
    watcher = Watchdantic(WatchdanticConfig(debounce_seconds=0.0))

    @watcher.triggers_on(TestModel, str("*data.jsonl"))
    def handle(models: List[TestModel], path: Path) -> None:
        print(f"  Triggered. Triggered by model: {models}")
        events.append(models)

    watcher.start(tmp_path)
    time.sleep(0.1)  # Add small delay to ensure observer is ready
    # Create a jsonl file with one line
    f = tmp_path / "data.jsonl"
    print(f"File: {f}")
    f.write_text(json.dumps({"x": 42}) + "\n", encoding="utf-8")
    time.sleep(0.15)  # Add small delay to ensure observer is ready
    assert _wait_until(lambda: len(events) == 1, timeout=2)
    assert events[0][0].x == 42

    watcher.stop()


def test_multiple_handlers_and_patterns(tmp_path: Path) -> None:
    a_hits: List[Path] = []
    b_hits: List[Path] = []

    # Use zero debounce time
    watcher = Watchdantic(WatchdanticConfig(debounce_seconds=0.0))

    @watcher.triggers_on(TestModel, str("a_*.jsonl"))
    def handle_a(models: List[TestModel], path: Path) -> None:
        print(f"  A Triggered. Triggered by model: {models}")
        a_hits.append(path)

    @watcher.triggers_on(TestModel, str("b_*.jsonl"))
    def handle_b(models: List[TestModel], path: Path) -> None:
        print(f"  B Triggered. Triggered by model: {models}")
        b_hits.append(path)

    watcher.start(tmp_path)
    time.sleep(0.1)

    print(f"\nBefore:")
    print(f"   A hits: {a_hits}")
    print(f"   B hits: {b_hits}")

    (tmp_path / "a_1.jsonl").write_text('{"x": 1}\n', encoding="utf-8")
    (tmp_path / "b_1.jsonl").write_text('{"x": 2}\n', encoding="utf-8")
    time.sleep(0.1)  # Add small delay to ensure file events are processed

    print(f"After:")
    print(f"   A hits: {a_hits}")
    print(f"   B hits: {b_hits}\n")

    assert _wait_until(lambda: len(a_hits) == 1 and len(b_hits) == 1, timeout=2.0)

    watcher.stop()
