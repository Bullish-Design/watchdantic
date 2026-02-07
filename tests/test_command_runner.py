"""Tests for command action runner."""

from __future__ import annotations

from pathlib import Path

import pytest

from watchdantic.engine.actions.command import ActionResult, build_env, run_command
from watchdantic.engine.config_models import ActionConfig
from watchdantic.engine.events import FileEvent
from watchdantic.exceptions import ActionError


def _evt(rel: str = "test.py") -> FileEvent:
    return FileEvent(
        change="modified",
        path_abs=Path(f"/fake/{rel}"),
        path_rel=Path(rel),
        is_dir=False,
        watch_name="w",
    )


class TestBuildEnv:
    def test_context_vars_present(self, tmp_path: Path):
        action = ActionConfig(name="a", cmd=["echo"])
        events = [_evt()]
        env = build_env(action, events, "rule1", "watch1", tmp_path)
        assert env["WATCHDANTIC_REPO_ROOT"] == str(tmp_path)
        assert env["WATCHDANTIC_RULE_NAME"] == "rule1"
        assert env["WATCHDANTIC_WATCH_NAME"] == "watch1"
        assert env["WATCHDANTIC_EVENT_COUNT"] == "1"
        assert "WATCHDANTIC_EVENTS_JSON" in env

    def test_user_env_override(self, tmp_path: Path):
        action = ActionConfig(name="a", cmd=["echo"], env={"MY_VAR": "hello"})
        env = build_env(action, [_evt()], "r", "w", tmp_path)
        assert env["MY_VAR"] == "hello"


class TestRunCommand:
    def test_successful_command(self, tmp_path: Path):
        action = ActionConfig(name="echo", cmd=["echo", "hello"])
        result = run_command(action, [_evt()], "r", "w", tmp_path)
        assert isinstance(result, ActionResult)
        assert result.exit_code == 0
        assert "hello" in result.stdout
        assert result.timed_out is False
        assert result.duration_ms >= 0

    def test_failing_command(self, tmp_path: Path):
        action = ActionConfig(name="fail", cmd=["bash", "-c", "exit 3"])
        result = run_command(action, [_evt()], "r", "w", tmp_path)
        assert result.exit_code == 3

    def test_stderr_captured(self, tmp_path: Path):
        action = ActionConfig(name="err", cmd=["bash", "-c", "echo oops >&2"])
        result = run_command(action, [_evt()], "r", "w", tmp_path)
        assert "oops" in result.stderr

    def test_timeout(self, tmp_path: Path):
        action = ActionConfig(name="slow", cmd=["sleep", "10"], timeout_s=1)
        result = run_command(action, [_evt()], "r", "w", tmp_path)
        assert result.timed_out is True
        assert result.exit_code == -1

    def test_cwd_respected(self, tmp_path: Path):
        sub = tmp_path / "subdir"
        sub.mkdir()
        action = ActionConfig(name="pwd", cmd=["pwd"], cwd="subdir")
        result = run_command(action, [_evt()], "r", "w", tmp_path)
        assert result.exit_code == 0
        assert "subdir" in result.stdout

    def test_shell_mode(self, tmp_path: Path):
        action = ActionConfig(
            name="shell", cmd=["echo $WATCHDANTIC_RULE_NAME"], shell=True
        )
        result = run_command(action, [_evt()], "myrule", "w", tmp_path)
        assert result.exit_code == 0
        assert "myrule" in result.stdout

    def test_nonexistent_command_raises(self, tmp_path: Path):
        action = ActionConfig(name="bad", cmd=["nonexistent_cmd_xyz_123"])
        with pytest.raises(ActionError, match="Failed to execute"):
            run_command(action, [_evt()], "r", "w", tmp_path)

    def test_env_passed_to_command(self, tmp_path: Path):
        action = ActionConfig(
            name="env",
            cmd=["bash", "-c", "echo $CUSTOM_VAR"],
            env={"CUSTOM_VAR": "test_value"},
        )
        result = run_command(action, [_evt()], "r", "w", tmp_path)
        assert "test_value" in result.stdout

    def test_marker_file_written(self, tmp_path: Path):
        marker = tmp_path / "triggered.txt"
        action = ActionConfig(
            name="marker",
            cmd=["bash", "-c", f"echo triggered > {marker}"],
        )
        result = run_command(action, [_evt()], "r", "w", tmp_path)
        assert result.exit_code == 0
        assert marker.read_text().strip() == "triggered"
