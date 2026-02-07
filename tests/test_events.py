"""Tests for event normalization."""

from __future__ import annotations

import json
from pathlib import Path

from watchfiles import Change

from watchdantic.engine.events import (
    CHANGE_MAP,
    FileEvent,
    events_to_json,
    normalize_changes,
)


class TestFileEvent:
    def test_basic_properties(self, tmp_path: Path):
        evt = FileEvent(
            change="added",
            path_abs=tmp_path / "src" / "foo.py",
            path_rel=Path("src/foo.py"),
            is_dir=False,
            watch_name="repo",
        )
        assert evt.change == "added"
        assert evt.path_rel_posix == "src/foo.py"
        assert evt.is_dir is False

    def test_to_dict(self, tmp_path: Path):
        evt = FileEvent(
            change="modified",
            path_abs=tmp_path / "a.txt",
            path_rel=Path("a.txt"),
            is_dir=False,
            watch_name="w1",
        )
        d = evt.to_dict()
        assert d["change"] == "modified"
        assert d["path_rel"] == "a.txt"
        assert d["watch_name"] == "w1"

    def test_frozen(self, tmp_path: Path):
        evt = FileEvent(
            change="deleted",
            path_abs=tmp_path / "x",
            path_rel=Path("x"),
            is_dir=False,
            watch_name="w",
        )
        import pytest
        with pytest.raises(AttributeError):
            evt.change = "added"  # type: ignore


class TestNormalizeChanges:
    def test_basic_normalization(self, tmp_path: Path):
        # Create a file so is_dir detection works
        f = tmp_path / "file.txt"
        f.write_text("content")
        raw = {(Change.modified, str(f))}
        events = normalize_changes(raw, tmp_path, "w")
        assert len(events) == 1
        assert events[0].change == "modified"
        assert events[0].path_rel == Path("file.txt")
        assert events[0].watch_name == "w"
        assert events[0].is_dir is False

    def test_multiple_changes(self, tmp_path: Path):
        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text("")
        f2.write_text("")
        raw = {(Change.added, str(f1)), (Change.modified, str(f2))}
        events = normalize_changes(raw, tmp_path, "w")
        assert len(events) == 2
        changes = {e.change for e in events}
        assert changes == {"added", "modified"}

    def test_deleted_file_is_not_dir(self, tmp_path: Path):
        # Deleted path doesn't exist
        raw = {(Change.deleted, str(tmp_path / "gone.txt"))}
        events = normalize_changes(raw, tmp_path, "w")
        assert len(events) == 1
        assert events[0].change == "deleted"
        assert events[0].is_dir is False

    def test_paths_outside_repo_skipped(self, tmp_path: Path):
        raw = {(Change.added, "/totally/outside/path.txt")}
        events = normalize_changes(raw, tmp_path, "w")
        assert len(events) == 0

    def test_directory_detected(self, tmp_path: Path):
        d = tmp_path / "subdir"
        d.mkdir()
        raw = {(Change.added, str(d))}
        events = normalize_changes(raw, tmp_path, "w")
        assert len(events) == 1
        assert events[0].is_dir is True


class TestEventsToJson:
    def test_serialization(self, tmp_path: Path):
        events = [
            FileEvent(
                change="added",
                path_abs=tmp_path / "f.py",
                path_rel=Path("f.py"),
                is_dir=False,
                watch_name="w",
            )
        ]
        result = json.loads(events_to_json(events))
        assert len(result) == 1
        assert result[0]["change"] == "added"
        assert result[0]["path_rel"] == "f.py"


class TestChangeMap:
    def test_all_changes_mapped(self):
        assert Change.added in CHANGE_MAP
        assert Change.modified in CHANGE_MAP
        assert Change.deleted in CHANGE_MAP
        assert CHANGE_MAP[Change.added] == "added"
        assert CHANGE_MAP[Change.modified] == "modified"
        assert CHANGE_MAP[Change.deleted] == "deleted"
