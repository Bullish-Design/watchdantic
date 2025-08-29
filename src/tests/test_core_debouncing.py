# src/tests/test_core_debouncing.py
import time
from pathlib import Path
from threading import Event

from watchdantic.core.debouncing import DebounceManager


def test_debounce_zero_fires_immediately(tmp_path: Path) -> None:
    dm = DebounceManager()
    fp = tmp_path / "a.jsonl"
    fired = Event()

    # A debounce of <= 0 should execute the callback immediately (synchronously)
    dm.schedule_processing(fp, 0.0, fired.set)
    assert fired.is_set()

    fired.clear()
    dm.schedule_processing(fp, -1.0, fired.set)
    assert fired.is_set()


def test_debounce_timer_semantics(tmp_path: Path) -> None:
    """
    Tests that a callback is fired after the debounce window and that
    subsequent calls within the window reset the timer.
    """
    dm = DebounceManager()
    fp = tmp_path / "b.jsonl"
    processed_events = []

    def my_callback():
        processed_events.append(time.time())

    # Schedule once and wait for it to fire
    dm.schedule_processing(fp, 0.1, my_callback)
    time.sleep(0.15)
    assert len(processed_events) == 1

    # Schedule again, then reschedule mid-window
    dm.schedule_processing(fp, 0.2, my_callback)
    time.sleep(0.1)
    dm.schedule_processing(fp, 0.2, my_callback)  # Reset timer
    time.sleep(0.15)  # Not enough time since reset
    assert len(processed_events) == 1  # Should not have fired again yet
    time.sleep(0.1)  # Enough time has now passed
    assert len(processed_events) == 2  # Should have fired now


def test_temporary_exclusion(tmp_path: Path) -> None:
    dm = DebounceManager()
    fp = tmp_path / "c.jsonl"
    processed_events = []

    # While a file is excluded, no callbacks should be scheduled for it
    dm.exclude_file_temporarily(fp, 0.2)
    assert dm.is_file_excluded(fp) is True
    dm.schedule_processing(fp, 0.05, lambda: processed_events.append(1))

    time.sleep(0.1)
    # The callback should not have fired
    assert len(processed_events) == 0

    # After the exclusion period, it should work normally
    time.sleep(0.15)  # Total time > 0.2s
    assert dm.is_file_excluded(fp) is False
    dm.schedule_processing(fp, 0.05, lambda: processed_events.append(1))
    time.sleep(0.1)
    assert len(processed_events) == 1
