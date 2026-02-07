"""Tests for TOML config loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from watchdantic.engine.config_loader import find_config, load_config
from watchdantic.exceptions import ConfigurationError


class TestLoadConfig:
    def test_load_valid(self, sample_config_path: Path):
        config = load_config(sample_config_path)
        assert config.version == 1
        assert len(config.watch) == 1
        assert config.watch[0].name == "repo"
        assert len(config.action) == 1
        assert config.action[0].name == "echo_test"
        assert len(config.rule) == 1
        assert config.rule[0].name == "on_change"

    def test_missing_file(self, tmp_path: Path):
        with pytest.raises(ConfigurationError, match="not found"):
            load_config(tmp_path / "nonexistent.toml")

    def test_invalid_toml(self, tmp_path: Path):
        bad = tmp_path / "watch.toml"
        bad.write_text("[invalid toml{")
        with pytest.raises(ConfigurationError, match="Invalid TOML"):
            load_config(bad)

    def test_validation_error(self, tmp_path: Path):
        bad = tmp_path / "watch.toml"
        bad.write_text("""\
version = 1
[[rule]]
name = "r"
watch = "nonexistent"
on = ["added"]
match = ["*"]
do = ["nonexistent"]
""")
        with pytest.raises(ConfigurationError, match="validation error"):
            load_config(bad)


class TestFindConfig:
    def test_finds_in_cwd(self, tmp_path: Path):
        (tmp_path / "watch.toml").write_text("version = 1\n")
        result = find_config(tmp_path)
        assert result == tmp_path / "watch.toml"

    def test_finds_in_parent(self, tmp_path: Path):
        (tmp_path / "watch.toml").write_text("version = 1\n")
        child = tmp_path / "sub" / "deep"
        child.mkdir(parents=True)
        result = find_config(child)
        assert result == tmp_path / "watch.toml"

    def test_not_found_raises(self, tmp_path: Path):
        empty = tmp_path / "empty_subdir"
        empty.mkdir()
        with pytest.raises(ConfigurationError, match="No watch.toml"):
            find_config(empty)
