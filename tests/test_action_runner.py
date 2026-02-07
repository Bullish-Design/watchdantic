"""Tests for action runner (rule-level orchestration)."""

from __future__ import annotations

from pathlib import Path

from watchdantic.engine.actions.runner import run_rule_actions
from watchdantic.engine.config_models import ActionConfig
from watchdantic.engine.events import FileEvent


def _evt() -> FileEvent:
    return FileEvent(
        change="modified",
        path_abs=Path("/fake/a.py"),
        path_rel=Path("a.py"),
        is_dir=False,
        watch_name="w",
    )


class TestRunRuleActions:
    def test_all_succeed(self, tmp_path: Path):
        actions = [
            ActionConfig(name="a1", cmd=["echo", "one"]),
            ActionConfig(name="a2", cmd=["echo", "two"]),
        ]
        results = run_rule_actions(actions, [_evt()], "r", "w", tmp_path, False)
        assert len(results) == 2
        assert all(r.exit_code == 0 for r in results)

    def test_stop_on_error(self, tmp_path: Path):
        actions = [
            ActionConfig(name="fail", cmd=["bash", "-c", "exit 1"]),
            ActionConfig(name="skip", cmd=["echo", "should not run"]),
        ]
        results = run_rule_actions(actions, [_evt()], "r", "w", tmp_path, False)
        assert len(results) == 1
        assert results[0].exit_code == 1

    def test_continue_on_error(self, tmp_path: Path):
        actions = [
            ActionConfig(name="fail", cmd=["bash", "-c", "exit 1"]),
            ActionConfig(name="ok", cmd=["echo", "still runs"]),
        ]
        results = run_rule_actions(actions, [_evt()], "r", "w", tmp_path, True)
        assert len(results) == 2
        assert results[0].exit_code == 1
        assert results[1].exit_code == 0
