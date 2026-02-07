"""Tests for CLI commands."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from watchdantic.cli import cmd_check, cmd_init, main


class TestCmdCheck:
    def test_valid_config(self, sample_config_path: Path, capsys):
        class Args:
            config = str(sample_config_path)

        result = cmd_check(Args())
        assert result == 0
        captured = capsys.readouterr()
        assert "Config OK" in captured.out

    def test_invalid_config(self, tmp_path: Path, capsys):
        bad = tmp_path / "watch.toml"
        bad.write_text("not valid {{")

        class Args:
            config = str(bad)

        result = cmd_check(Args())
        assert result == 1
        captured = capsys.readouterr()
        assert "ERROR" in captured.err


class TestCmdInit:
    def test_creates_file(self, tmp_path: Path, capsys):
        out_path = tmp_path / "watch.toml"
        out_str = str(out_path)

        class Args:
            output = out_str
            force = False

        result = cmd_init(Args())
        assert result == 0
        assert out_path.exists()
        content = out_path.read_text()
        assert "version = 1" in content
        assert "[[watch]]" in content

    def test_refuses_overwrite_without_force(self, tmp_path: Path, capsys):
        out_path = tmp_path / "watch.toml"
        out_path.write_text("existing")
        out_str = str(out_path)

        class Args:
            output = out_str
            force = False

        result = cmd_init(Args())
        assert result == 1
        assert out_path.read_text() == "existing"

    def test_force_overwrite(self, tmp_path: Path, capsys):
        out_path = tmp_path / "watch.toml"
        out_path.write_text("old")
        out_str = str(out_path)

        class Args:
            output = out_str
            force = True

        result = cmd_init(Args())
        assert result == 0
        assert "version = 1" in out_path.read_text()


class TestMainEntryPoint:
    def test_no_args_shows_help(self, capsys):
        result = main([])
        assert result == 1

    def test_version(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["--version"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "0.2.0" in captured.out

    def test_check_subcommand(self, sample_config_path: Path, capsys):
        result = main(["check", "-c", str(sample_config_path)])
        assert result == 0
