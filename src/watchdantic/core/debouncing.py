from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, Set
from threading import Lock, Timer

from pydantic import BaseModel, Field, PrivateAttr


class DebounceManager(BaseModel):
    """
    Simplified per-file debouncing with temporary exclusions and delayed callbacks.
    Provides a single-method API for debounce checking with automatic timer management.
    """

    # Files currently excluded from processing
    excluded_files: Set[Path] = Field(default_factory=set)

    # Private attributes for thread safety
    _active_timers: Dict[Path, Timer] = PrivateAttr(default_factory=dict)
    _lock: Lock = PrivateAttr(default_factory=Lock)

    model_config = dict(arbitrary_types_allowed=True)

    def schedule_processing(self, file_path: Path, debounce_seconds: float, callback: Callable[[], None]) -> None:
        """
        Schedules a callback to run for a file after a debounce period.

        If called again for the same file before the timer expires, the previous
        timer is cancelled and a new one is started. Does nothing if the file
        is temporarily excluded.
        """
        # FIX: Check for exclusion before proceeding
        if self.is_file_excluded(file_path):
            return

        if debounce_seconds <= 0:
            callback()
            return

        with self._lock:
            # Cancel existing timer for this file
            if file_path in self._active_timers:
                old_timer = self._active_timers.pop(file_path)
                if old_timer.is_alive():
                    old_timer.cancel()

            # The wrapper ensures we remove the timer from the active dict
            # before the real callback is invoked.
            def timer_callback_wrapper():
                with self._lock:
                    self._active_timers.pop(file_path, None)
                callback()

            timer = Timer(debounce_seconds, timer_callback_wrapper)
            timer.daemon = True
            self._active_timers[file_path] = timer
            timer.start()

    def exclude_file_temporarily(self, file_path: Path, duration: float) -> None:
        """Temporarily exclude a file from processing (e.g., for write operations)."""

        def remove_exclusion():
            with self._lock:
                self.excluded_files.discard(file_path)

        with self._lock:
            self.excluded_files.add(file_path)
            timer = Timer(duration, remove_exclusion)
            timer.daemon = True
            timer.start()

    def is_file_excluded(self, file_path: Path) -> bool:
        """Check if a file is currently excluded from processing."""
        with self._lock:
            return file_path in self.excluded_files

    def clear_all(self) -> None:
        """Cancel all timers and clear all state (for shutdown)."""
        with self._lock:
            for timer in self._active_timers.values():
                if timer.is_alive():
                    timer.cancel()
            self._active_timers.clear()
            self.excluded_files.clear()
