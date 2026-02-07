"""Normalized file event model."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from watchfiles import Change

EventType = Literal["added", "modified", "deleted"]

# Map watchfiles Change enum to our string event types.
CHANGE_MAP: dict[Change, EventType] = {
    Change.added: "added",
    Change.modified: "modified",
    Change.deleted: "deleted",
}


@dataclass(frozen=True, slots=True)
class FileEvent:
    """A single normalized filesystem change event."""

    change: EventType
    path_abs: Path
    path_rel: Path
    is_dir: bool
    watch_name: str

    @property
    def path_rel_posix(self) -> str:
        """Relative path as POSIX string (for glob matching)."""
        return self.path_rel.as_posix()

    def to_dict(self) -> dict:
        return {
            "change": self.change,
            "path_abs": str(self.path_abs),
            "path_rel": self.path_rel_posix,
            "is_dir": self.is_dir,
            "watch_name": self.watch_name,
        }


def normalize_changes(
    raw_changes: set[tuple[Change, str]],
    repo_root: Path,
    watch_name: str,
) -> list[FileEvent]:
    """Convert raw watchfiles changes into FileEvent objects."""
    events: list[FileEvent] = []
    for change, path_str in raw_changes:
        abs_path = Path(path_str)
        try:
            rel_path = abs_path.relative_to(repo_root)
        except ValueError:
            # Path is outside repo root; skip
            continue

        event_type = CHANGE_MAP.get(change)
        if event_type is None:
            continue

        # For deleted paths, the file no longer exists, so is_dir is best-effort.
        is_dir = abs_path.is_dir() if abs_path.exists() else False

        events.append(
            FileEvent(
                change=event_type,
                path_abs=abs_path,
                path_rel=rel_path,
                is_dir=is_dir,
                watch_name=watch_name,
            )
        )
    return events


def events_to_json(events: list[FileEvent]) -> str:
    """Serialize events to JSON string for env var passing."""
    return json.dumps([e.to_dict() for e in events])
