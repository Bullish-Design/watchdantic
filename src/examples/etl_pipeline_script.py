"""ETL pipeline example with Watchdantic - transform and enrich data."""

from __future__ import annotations
from pathlib import Path
from typing import List, Dict
from datetime import datetime

from pydantic import BaseModel, Field
from watchdantic import Watchdantic, WatchdanticConfig
from watchdantic.core.logging import WatchdanticLogger

WatchdanticLogger.model_rebuild()


class RawUserEvent(BaseModel):
    """Raw user event from external system."""

    user_id: str
    event_type: str
    timestamp: datetime
    properties: Dict[str, str] = Field(default_factory=dict)


class EnrichedUserEvent(BaseModel):
    """Enriched user event with additional metadata."""

    user_id: str
    event_type: str
    timestamp: datetime
    properties: Dict[str, str]
    enriched_at: datetime
    source_file: str
    category: str
    priority: str


def enrich_event(raw_event: RawUserEvent, source_file: Path) -> EnrichedUserEvent:
    """Transform raw event into enriched event."""
    # Simple categorization logic
    category_map = {
        "login": "authentication",
        "logout": "authentication",
        "purchase": "transaction",
        "view_product": "engagement",
        "add_to_cart": "engagement",
    }

    priority_map = {
        "purchase": "high",
        "login": "medium",
        "logout": "low",
        "view_product": "low",
        "add_to_cart": "medium",
    }

    return EnrichedUserEvent(
        user_id=raw_event.user_id,
        event_type=raw_event.event_type,
        timestamp=raw_event.timestamp,
        properties=raw_event.properties,
        enriched_at=datetime.now(),
        source_file=source_file.name,
        category=category_map.get(raw_event.event_type, "unknown"),
        priority=priority_map.get(raw_event.event_type, "low"),
    )


def main():
    """ETL pipeline with input transformation and output monitoring."""

    # Configure with logging for better observability
    config = WatchdanticConfig(enable_logging=True, log_level="INFO", default_debounce=2.0)

    watcher = Watchdantic(config)

    @watcher.triggers_on(
        RawUserEvent,
        "input/*.jsonl",
        continue_on_error=True,  # Process valid events even if some are invalid
    )
    def transform_events(models: List[RawUserEvent], file_path: Path):
        """Transform raw events to enriched events."""
        print(f"Processing {len(models)} raw events from {file_path.name}")

        # Transform each event
        enriched_events = []
        for raw_event in models:
            enriched = enrich_event(raw_event, file_path)
            enriched_events.append(enriched)

        # Write to output directory
        output_path = Path("output") / f"enriched_{file_path.name}"
        watcher.write_models(enriched_events, output_path)

        print(f"  -> Wrote {len(enriched_events)} enriched events to {output_path.name}")

    @watcher.triggers_on(EnrichedUserEvent, "output/*.jsonl")
    def generate_summary(models: List[EnrichedUserEvent], file_path: Path):
        """Generate summary statistics from enriched events."""
        print(f"Generating summary for {len(models)} enriched events from {file_path.name}")

        # Calculate statistics
        category_counts = {}
        priority_counts = {}
        user_counts = set()

        for event in models:
            category_counts[event.category] = category_counts.get(event.category, 0) + 1
            priority_counts[event.priority] = priority_counts.get(event.priority, 0) + 1
            user_counts.add(event.user_id)

        # Create summary
        summary = {
            "file": file_path.name,
            "timestamp": datetime.now().isoformat(),
            "total_events": len(models),
            "unique_users": len(user_counts),
            "categories": category_counts,
            "priorities": priority_counts,
        }

        # Write summary (as JSON for single object)
        summary_path = Path("summaries") / f"summary_{file_path.stem}.json"
        summary_path.parent.mkdir(exist_ok=True)

        # Convert dict to Pydantic model for writing
        class Summary(BaseModel):
            file: str
            timestamp: str
            total_events: int
            unique_users: int
            categories: Dict[str, int]
            priorities: Dict[str, int]

        summary_model = Summary(**summary)
        watcher.write_models([summary_model], summary_path)

        print(f"  -> Summary: {len(models)} events, {len(user_counts)} users")
        print(f"     Categories: {category_counts}")

    # Create directories
    for dir_name in ["input", "output", "summaries"]:
        Path(dir_name).mkdir(exist_ok=True)

    print("Starting ETL pipeline...")
    print("  - Watching input/*.jsonl for raw events")
    print("  - Will transform and write to output/*.jsonl")
    print("  - Will generate summaries in summaries/*.json")

    watcher.start(".")

    # Generate sample data
    sample_events = [
        RawUserEvent(
            user_id="user123",
            event_type="login",
            timestamp=datetime.now(),
            properties={"ip": "192.168.1.1", "browser": "chrome"},
        ),
        RawUserEvent(
            user_id="user123",
            event_type="view_product",
            timestamp=datetime.now(),
            properties={"product_id": "prod456", "category": "electronics"},
        ),
        RawUserEvent(
            user_id="user456",
            event_type="purchase",
            timestamp=datetime.now(),
            properties={"product_id": "prod456", "amount": "99.99"},
        ),
    ]

    print("Writing sample events to input/sample_events.jsonl...")
    watcher.write_models(sample_events, "input/sample_events.jsonl")

    try:
        print("\nETL pipeline running... Add files to input/ to see processing")
        print("Press Ctrl+C to stop")

        import time

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping ETL pipeline...")
        watcher.stop()
        print("Done.")


if __name__ == "__main__":
    main()

