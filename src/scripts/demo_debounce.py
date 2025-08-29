#!/usr/bin/env python3
from __future__ import annotations
import time
from pathlib import Path
from watchdantic.core.models import DebounceManager


def main() -> None:
    dm = DebounceManager()
    fp = Path("demo.jsonl")

    print("=== Scenario A: no mid-window touch (fires once) ===")
    print("event #1 ->", dm.should_process_file(fp, 1.0))  # False (arms)
    time.sleep(1.15)  # > 1.0s
    print("after 1.15s ->", dm.should_process_file(fp, 1.0))  # True (fires once)

    print("\n=== Scenario B: touch mid-window (reschedules) ===")
    print("event #2 ->", dm.should_process_file(fp, 1.0))  # False (arms)
    time.sleep(0.7)  # still within 1.0s
    print("event #3 (mid) ->", dm.should_process_file(fp, 1.0))  # False (rescheduled)
    time.sleep(0.4)  # not enough since reschedule
    print("after +0.4s ->", dm.should_process_file(fp, 1.0))  # False
    time.sleep(0.8)  # total 1.2s since reschedule
    # tiny buffer to avoid race with Timer thread starting the callback
    time.sleep(0.05)
    print("after +0.8s (+50ms buffer) ->", dm.should_process_file(fp, 1.0))  # True


if __name__ == "__main__":
    main()
