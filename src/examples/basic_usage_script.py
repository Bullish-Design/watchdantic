#!/usr/bin/env python3

"""Basic log processing with Watchdantic."""

from __future__ import annotations
from pathlib import Path
from typing import List
from datetime import datetime

from pydantic import BaseModel, Field
from watchdantic import Watchdantic


class LogEntry(BaseModel):
    """Application log entry model."""

    timestamp: datetime
    level: str = Field(pattern=r"^(DEBUG|INFO|WARN|ERROR|FATAL)$")
    message: str
    source: str = Field(default="app")


def main():
    """Main log processing example."""
    watcher = Watchdantic()

    @watcher.triggers_on(LogEntry, "logs/*.jsonl")
    def process_logs(models: List[LogEntry], file_path: Path):
        """Process incoming log entries."""
        error_count = sum(1 for log in models if log.level == "ERROR")
        fatal_count = sum(1 for log in models if log.level == "FATAL")

        print(f"Processed {len(models)} log entries from {file_path.name}")

        if error_count > 0:
            print(f"  - Found {error_count} ERROR entries")

        if fatal_count > 0:
            print(f"  - Found {fatal_count} FATAL entries - alerting system!")

        # Write summary to processed logs
        if error_count > 0 or fatal_count > 0:
            summary = LogEntry(
                timestamp=datetime.now(),
                level="INFO",
                message=f"Processed {file_path.name}: {error_count} errors, {fatal_count} fatal",
                source="log_processor",
            )
            watcher.write_models([summary], "logs/processing_summary.jsonl")

    # Create test data directory
    Path("logs").mkdir(exist_ok=True)

    # Start monitoring
    print("Starting log processor... watching logs/*.jsonl")
    watcher.start(".")

    # Generate sample log data for demonstration
    sample_logs = [
        LogEntry(timestamp=datetime.now(), level="INFO", message="Application started successfully"),
        LogEntry(timestamp=datetime.now(), level="ERROR", message="Database connection timeout"),
        LogEntry(timestamp=datetime.now(), level="WARN", message="High memory usage detected"),
    ]

    # Write test data - this will trigger the handler
    print("Writing test log data...")
    watcher.write_models(sample_logs, "logs/app.jsonl")

    # Keep running
    try:
        print("Log processor running... Press Ctrl+C to stop")
        print("Add .jsonl files to the logs/ directory to see processing in action")

        import time

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping log processor...")
        watcher.stop()
        print("Done.")


if __name__ == "__main__":
    main()

