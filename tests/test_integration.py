"""Integration test: full engine loop with file changes triggering actions."""

from __future__ import annotations

import textwrap
import threading
import time
from pathlib import Path

import pytest

from watchdantic.engine.config_loader import load_config
from watchdantic.engine.engine import Engine


@pytest.fixture
def integration_repo(tmp_path: Path) -> tuple[Path, Path]:
    """Set up a repo with watch.toml that writes a marker on file change."""
    marker = tmp_path / "marker.txt"
    watched_dir = tmp_path / "src"
    watched_dir.mkdir()

    config_text = textwrap.dedent(f"""\
        version = 1

        [engine]
        repo_root = "."
        debounce_ms = 100
        log_level = "DEBUG"

        [[watch]]
        name = "src"
        paths = ["src"]
        debounce_ms = 100

        [[action]]
        name = "write_marker"
        type = "command"
        cmd = ["bash", "-c", "echo triggered >> {marker}"]

        [[rule]]
        name = "on_py_change"
        watch = "src"
        on = ["added", "modified"]
        match = ["src/**/*.py"]
        do = ["write_marker"]
    """)
    config_path = tmp_path / "watch.toml"
    config_path.write_text(config_text)
    return tmp_path, marker


def test_engine_detects_file_change(integration_repo: tuple[Path, Path]):
    """End-to-end: create a file, engine sees it, command writes marker."""
    repo_root, marker = integration_repo
    config_path = repo_root / "watch.toml"
    config = load_config(config_path)
    resolved_root = config.resolve_paths(config_path.parent)

    engine = Engine(config, resolved_root)

    # Run engine in background thread
    engine_thread = threading.Thread(target=engine.run_forever, daemon=True)
    engine_thread.start()

    try:
        # Give watchfiles time to start
        time.sleep(0.5)

        # Create a file in the watched directory
        test_file = repo_root / "src" / "hello.py"
        test_file.write_text("print('hello')\n")

        # Wait for debounce + action execution
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if marker.exists() and marker.read_text().strip():
                break
            time.sleep(0.2)

        assert marker.exists(), "Marker file was not created"
        content = marker.read_text().strip()
        assert "triggered" in content
    finally:
        engine.stop()
        engine_thread.join(timeout=5.0)


def test_engine_ignores_non_matching_files(integration_repo: tuple[Path, Path]):
    """Non-matching files should not trigger actions."""
    repo_root, marker = integration_repo
    config_path = repo_root / "watch.toml"
    config = load_config(config_path)
    resolved_root = config.resolve_paths(config_path.parent)

    engine = Engine(config, resolved_root)
    engine_thread = threading.Thread(target=engine.run_forever, daemon=True)
    engine_thread.start()

    try:
        time.sleep(0.5)

        # Create a non-Python file (should not trigger)
        (repo_root / "src" / "data.txt").write_text("not python\n")

        time.sleep(1.5)
        assert not marker.exists(), "Marker should not exist for non-matching file"
    finally:
        engine.stop()
        engine_thread.join(timeout=5.0)


def test_engine_delete_event(tmp_path: Path):
    """Engine sees delete events."""
    marker = tmp_path / "delete_marker.txt"
    watched_dir = tmp_path / "src"
    watched_dir.mkdir()

    # Pre-create a file to delete
    target = watched_dir / "to_delete.py"
    target.write_text("delete me\n")

    config_text = textwrap.dedent(f"""\
        version = 1

        [engine]
        repo_root = "."
        debounce_ms = 100
        log_level = "DEBUG"

        [[watch]]
        name = "src"
        paths = ["src"]
        debounce_ms = 100

        [[action]]
        name = "on_delete"
        type = "command"
        cmd = ["bash", "-c", "echo deleted >> {marker}"]

        [[rule]]
        name = "delete_rule"
        watch = "src"
        on = ["deleted"]
        match = ["src/**/*.py"]
        do = ["on_delete"]
    """)
    config_path = tmp_path / "watch.toml"
    config_path.write_text(config_text)

    config = load_config(config_path)
    resolved_root = config.resolve_paths(config_path.parent)
    engine = Engine(config, resolved_root)

    engine_thread = threading.Thread(target=engine.run_forever, daemon=True)
    engine_thread.start()

    try:
        time.sleep(0.5)
        target.unlink()

        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if marker.exists() and marker.read_text().strip():
                break
            time.sleep(0.2)

        assert marker.exists(), "Delete marker was not created"
        assert "deleted" in marker.read_text()
    finally:
        engine.stop()
        engine_thread.join(timeout=5.0)
