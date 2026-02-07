"""Tests for config model validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from watchdantic.engine.config_models import (
    ActionConfig,
    EngineConfig,
    RepoConfig,
    RuleConfig,
    WatchConfig,
)


class TestEngineConfig:
    def test_defaults(self):
        cfg = EngineConfig()
        assert cfg.repo_root == "."
        assert cfg.debounce_ms == 300
        assert cfg.step_ms is None
        assert cfg.use_default_filter is True
        assert cfg.log_level == "INFO"
        assert cfg.max_workers == 1

    def test_custom_values(self):
        cfg = EngineConfig(
            repo_root="/tmp",
            debounce_ms=500,
            step_ms=50,
            use_default_filter=False,
            ignore_dirs=[".git"],
            ignore_globs=["*.pyc"],
            log_level="DEBUG",
            max_workers=4,
        )
        assert cfg.debounce_ms == 500
        assert cfg.max_workers == 4

    def test_negative_debounce_rejected(self):
        with pytest.raises(ValidationError):
            EngineConfig(debounce_ms=-1)

    def test_invalid_log_level_rejected(self):
        with pytest.raises(ValidationError):
            EngineConfig(log_level="TRACE")

    def test_zero_max_workers_rejected(self):
        with pytest.raises(ValidationError):
            EngineConfig(max_workers=0)


class TestWatchConfig:
    def test_valid(self):
        cfg = WatchConfig(name="repo", paths=["."])
        assert cfg.name == "repo"

    def test_empty_paths_rejected(self):
        with pytest.raises(ValidationError):
            WatchConfig(name="repo", paths=[])

    def test_path_traversal_rejected(self):
        with pytest.raises(ValidationError, match="escape repo root"):
            WatchConfig(name="repo", paths=["../outside"])

    def test_relative_paths_ok(self):
        cfg = WatchConfig(name="repo", paths=["src/foo", "docs"])
        assert len(cfg.paths) == 2


class TestActionConfig:
    def test_valid_command(self):
        cfg = ActionConfig(name="build", cmd=["make", "all"])
        assert cfg.type == "command"
        assert cfg.shell is False

    def test_empty_cmd_rejected(self):
        with pytest.raises(ValidationError):
            ActionConfig(name="build", cmd=[])

    def test_cwd_traversal_rejected(self):
        with pytest.raises(ValidationError, match="escape repo root"):
            ActionConfig(name="build", cmd=["make"], cwd="../outside")

    def test_shell_mode(self):
        cfg = ActionConfig(name="build", cmd=["make all"], shell=True)
        assert cfg.shell is True

    def test_env_and_timeout(self):
        cfg = ActionConfig(
            name="build",
            cmd=["make"],
            env={"FOO": "bar"},
            timeout_s=60,
        )
        assert cfg.env == {"FOO": "bar"}
        assert cfg.timeout_s == 60


class TestRuleConfig:
    def test_valid(self):
        cfg = RuleConfig(
            name="r1",
            watch="repo",
            on=["added", "modified"],
            match=["**/*.py"],
            do=["build"],
        )
        assert cfg.continue_on_error is False

    def test_empty_on_rejected(self):
        with pytest.raises(ValidationError):
            RuleConfig(name="r1", watch="repo", on=[], match=["*"], do=["a"])

    def test_empty_match_rejected(self):
        with pytest.raises(ValidationError):
            RuleConfig(name="r1", watch="repo", on=["added"], match=[], do=["a"])

    def test_empty_do_rejected(self):
        with pytest.raises(ValidationError):
            RuleConfig(name="r1", watch="repo", on=["added"], match=["*"], do=[])

    def test_invalid_event_type_rejected(self):
        with pytest.raises(ValidationError):
            RuleConfig(
                name="r1",
                watch="repo",
                on=["created"],  # type: ignore
                match=["*"],
                do=["a"],
            )


class TestRepoConfig:
    def test_minimal_valid(self):
        cfg = RepoConfig(
            watch=[WatchConfig(name="w", paths=["."])],
            action=[ActionConfig(name="a", cmd=["echo"])],
            rule=[
                RuleConfig(name="r", watch="w", on=["added"], match=["*"], do=["a"])
            ],
        )
        assert cfg.version == 1

    def test_duplicate_watch_names_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate watch name"):
            RepoConfig(
                watch=[
                    WatchConfig(name="w", paths=["."]),
                    WatchConfig(name="w", paths=["src"]),
                ],
            )

    def test_duplicate_action_names_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate action name"):
            RepoConfig(
                watch=[WatchConfig(name="w", paths=["."]) ],
                action=[
                    ActionConfig(name="a", cmd=["echo"]),
                    ActionConfig(name="a", cmd=["ls"]),
                ],
            )

    def test_duplicate_rule_names_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate rule name"):
            RepoConfig(
                watch=[WatchConfig(name="w", paths=["."]) ],
                action=[ActionConfig(name="a", cmd=["echo"])],
                rule=[
                    RuleConfig(name="r", watch="w", on=["added"], match=["*"], do=["a"]),
                    RuleConfig(name="r", watch="w", on=["modified"], match=["*"], do=["a"]),
                ],
            )

    def test_rule_references_unknown_watch(self):
        with pytest.raises(ValidationError, match="unknown watch"):
            RepoConfig(
                watch=[WatchConfig(name="w", paths=["."]) ],
                action=[ActionConfig(name="a", cmd=["echo"])],
                rule=[
                    RuleConfig(name="r", watch="missing", on=["added"], match=["*"], do=["a"]),
                ],
            )

    def test_rule_references_unknown_action(self):
        with pytest.raises(ValidationError, match="unknown action"):
            RepoConfig(
                watch=[WatchConfig(name="w", paths=["."]) ],
                action=[ActionConfig(name="a", cmd=["echo"])],
                rule=[
                    RuleConfig(name="r", watch="w", on=["added"], match=["*"], do=["missing"]),
                ],
            )

    def test_resolve_paths(self, tmp_path):
        cfg = RepoConfig(engine=EngineConfig(repo_root="."))
        root = cfg.resolve_paths(tmp_path)
        assert root == tmp_path.resolve()
