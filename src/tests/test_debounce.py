from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional

import threading
import time

import pytest

# Import target
from watchdantic.core.models import DebounceManager


# ------------------------------
# Deterministic Fake Timer
# ------------------------------
class _FakeTimer:
    """
    Deterministic replacement for threading.Timer.

    Usage in tests:
      - Monkeypatch watchdantic.core.models.Timer = _FakeTimer
      - Call _FakeTimer.advance(delta) to elapse time and trigger due timers
    """

    _now: float = 0.0
    _timers: List["_FakeTimer"] = []

    def __init__(self, interval: float, function: Callable, args: Optional[list] = None, kwargs: Optional[dict] = None):
        self.interval = float(interval)
        self.function = function
        self.args = args or []
        self.kwargs = kwargs or {}
        self.start_time: Optional[float] = None
        self.fire_time: Optional[float] = None
        self._cancelled = False
        self._fired = False
        self._started = False
        _FakeTimer._timers.append(self)

    def start(self) -> None:
        self._started = True
        self.start_time = _FakeTimer._now
        self.fire_time = self.start_time + self.interval

    def cancel(self) -> None:
        self._cancelled = True

    def is_alive(self) -> bool:
        return self._started and (not self._cancelled) and (not self._fired)

    @classmethod
    def advance(cls, delta: float) -> None:
        """
        Advance fake time and fire all due timers in order of fire_time.
        """
        end = cls._now + float(delta)
        while True:
            # Select next due timer
            due = sorted(
                [
                    t
                    for t in cls._timers
                    if t._started and not t._cancelled and not t._fired and t.fire_time is not None
                ],
                key=lambda t: t.fire_time,  # type: ignore[arg-type]
            )
            if not due:
                cls._now = end
                return
            next_fire = due[0].fire_time
            if next_fire is None or next_fire > end:
                cls._now = end
                return
            # Jump to next fire time and trigger
            cls._now = next_fire
            # Fire all timers scheduled exactly now (stable)
            to_fire = [t for t in due if t.fire_time == cls._now]
            for t in to_fire:
                t._fired = True
                try:
                    t.function(*t.args, **t.kwargs)
                finally:
                    # nothing else
                    pass

    @classmethod
    def reset(cls) -> None:
        cls._now = 0.0
        cls._timers.clear()


@pytest.fixture(autouse=True)
def _patch_timer(monkeypatch: pytest.MonkeyPatch):
    # Patch only the DebounceManager's module reference to Timer
    import watchdantic.core.models as models_mod

    _FakeTimer.reset()
    monkeypatch.setattr(models_mod, "Timer", _FakeTimer)
    yield
    _FakeTimer.reset()


def test_basic_debouncing_behavior(tmp_path: Path) -> None:
    dm = DebounceManager()
    fp = tmp_path / "a.jsonl"

    # first event schedules timer; not ready yet
    dm.notify_file_event(fp, debounce_seconds=1.0)
    assert dm.is_file_ready(fp) is False

    # another event within debounce resets timer; still not ready
    dm.notify_file_event(fp, debounce_seconds=1.0)
    assert dm.is_file_ready(fp) is False

    # advance less than interval: still not ready
    _FakeTimer.advance(0.9)
    assert dm.is_file_ready(fp) is False

    # advance past interval: timer fires -> next call returns True once
    _FakeTimer.advance(0.2)
    assert dm.is_file_ready(fp) is True

    # subsequent call without a new event returns False
    assert dm.is_file_ready(fp) is False


def test_multiple_files_independent_timers(tmp_path: Path) -> None:
    dm = DebounceManager()
    a = tmp_path / "A.jsonl"
    b = tmp_path / "B.jsonl"

    dm.notify_file_event(a, 1.0)
    dm.notify_file_event(b, 1.5)
    assert dm.is_file_ready(a) is False
    assert dm.is_file_ready(b) is False

    # advance 1.0s -> A becomes ready
    _FakeTimer.advance(1.0)
    assert dm.is_file_ready(a) is True
    assert dm.is_file_ready(b) is False

    # advance additional 0.5s -> B becomes ready
    _FakeTimer.advance(0.5)
    assert dm.is_file_ready(b) is True


def test_timer_cancellation_and_rescheduling(tmp_path: Path) -> None:
    dm = DebounceManager()
    fp = tmp_path / "resched.jsonl"

    # schedule
    dm.notify_file_event(fp, 1.0)
    assert dm.is_file_ready(fp) is False

    # reschedule before firing
    dm.notify_file_event(fp, 1.0)
    assert dm.is_file_ready(fp) is False

    # advance exactly 1.0s: only latest timer should fire
    _FakeTimer.advance(1.0)
    assert dm.is_file_ready(fp) is True


def test_temporary_file_exclusions(tmp_path: Path) -> None:
    dm = DebounceManager()
    fp = tmp_path / "excluded.jsonl"

    dm.exclude_file_temporarily(fp, duration=2.0)

    # While excluded, should never schedule
    dm.notify_file_event(fp, 0.5)
    assert dm.is_file_ready(fp) is False

    _FakeTimer.advance(5.0)  # let exclusion expire
    # Now schedule; not ready yet
    dm.notify_file_event(fp, 0.5)
    assert dm.is_file_ready(fp) is False

    _FakeTimer.advance(0.5)
    assert dm.is_file_ready(fp) is True


def test_memory_cleanup_no_timer_leaks(tmp_path: Path) -> None:
    dm = DebounceManager()
    fp = tmp_path / "leaks.jsonl"

    # schedule
    dm.notify_file_event(fp, 0.5)
    assert dm.is_file_ready(fp) is False

    # let it fire -> internally removes from pending_timers
    _FakeTimer.advance(0.5)
    # consumption turns ready -> True
    assert dm.is_file_ready(fp) is True

    # also ensure cleanup doesn't choke on empty
    dm.cleanup_expired_timers()
    assert dm.pending_timers == {}


def test_cleanup_of_cancelled_timers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Simulate a cancelled timer and ensure cleanup removes it.
    """
    dm = DebounceManager()
    fp = tmp_path / "cancel.jsonl"

    dm.notify_file_event(fp, 10.0)  # long timer
    assert dm.is_file_ready(fp) is False

    # Find the fake timer and cancel it directly to simulate external cancel
    timers = [t for t in _FakeTimer._timers if t.is_alive()]
    assert timers, "expected at least one alive timer"
    timers[0].cancel()
    assert not timers[0].is_alive()

    # Now cleanup should remove it
    dm.cleanup_expired_timers()
    assert fp not in dm.pending_timers


def test_thread_safety_under_quick_succession(tmp_path: Path) -> None:
    """
    Simulate fast back-to-back calls that might occur from multiple FS events.
    No race conditions should occur; behavior should be consistent.
    """
    dm = DebounceManager()
    fp = tmp_path / "rapid.jsonl"

    # Rapid-fire event notifications
    for _ in range(10):
        dm.notify_file_event(fp, 0.2)
        assert dm.is_file_ready(fp) is False

    # Only after advancing beyond debounce should we see True (once)
    _FakeTimer.advance(0.25)
    assert dm.is_file_ready(fp) is True
    # Next call returns False
    assert dm.is_file_ready(fp) is False


def test_separated_api_independence(tmp_path: Path) -> None:
    """
    Test that is_file_ready() doesn't interfere with event scheduling.
    """
    dm = DebounceManager()
    fp = tmp_path / "independent.jsonl"

    # Schedule event
    dm.notify_file_event(fp, 1.0)

    # Multiple status checks shouldn't affect timer
    for _ in range(5):
        assert dm.is_file_ready(fp) is False

    # Timer should still fire after 1.0s
    _FakeTimer.advance(1.0)
    assert dm.is_file_ready(fp) is True


def test_notify_while_excluded_is_noop(tmp_path: Path) -> None:
    """
    Test that notify_file_event() during exclusion period is a no-op.
    """
    dm = DebounceManager()
    fp = tmp_path / "excluded_notify.jsonl"

    dm.exclude_file_temporarily(fp, duration=2.0)

    # Event notification during exclusion should be ignored
    dm.notify_file_event(fp, 0.5)
    assert len(dm.pending_timers) == 0  # No timer scheduled

    # Even after short time, nothing happens
    _FakeTimer.advance(1.0)
    assert dm.is_file_ready(fp) is False

    # Wait for exclusion to expire
    _FakeTimer.advance(2.0)

    # Now events work normally
    dm.notify_file_event(fp, 0.5)
    assert len(dm.pending_timers) == 1
    _FakeTimer.advance(0.5)
    assert dm.is_file_ready(fp) is True
