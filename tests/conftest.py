"""Shared test fixtures."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """Create a minimal repo directory structure."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "src").mkdir()
    return tmp_path


@pytest.fixture
def sample_toml() -> str:
    return textwrap.dedent("""\
        version = 1

        [engine]
        repo_root = "."
        debounce_ms = 100
        ignore_dirs = [".git"]
        ignore_globs = ["**/*.pyc"]
        log_level = "DEBUG"

        [[watch]]
        name = "repo"
        paths = ["."]

        [[action]]
        name = "echo_test"
        type = "command"
        cmd = ["echo", "hello"]

        [[rule]]
        name = "on_change"
        watch = "repo"
        on = ["added", "modified"]
        match = ["**/*.py"]
        do = ["echo_test"]
    """)


@pytest.fixture
def sample_config_path(tmp_repo: Path, sample_toml: str) -> Path:
    config_path = tmp_repo / "watch.toml"
    config_path.write_text(sample_toml)
    return config_path
