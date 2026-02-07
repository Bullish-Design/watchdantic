"""Tests for the dispatcher."""

from __future__ import annotations

from pathlib import Path

from watchdantic.engine.config_models import (
    ActionConfig,
    EngineConfig,
    RepoConfig,
    RuleConfig,
    WatchConfig,
)
from watchdantic.engine.dispatcher import Dispatcher
from watchdantic.engine.events import FileEvent


def _make_config(max_workers: int = 1) -> RepoConfig:
    return RepoConfig(
        engine=EngineConfig(max_workers=max_workers),
        watch=[WatchConfig(name="w", paths=["."]) ],
        action=[
            ActionConfig(name="echo1", cmd=["echo", "one"]),
            ActionConfig(name="echo2", cmd=["echo", "two"]),
        ],
        rule=[
            RuleConfig(
                name="r",
                watch="w",
                on=["added"],
                match=["**/*"],
                do=["echo1", "echo2"],
            )
        ],
    )


def _evt() -> FileEvent:
    return FileEvent(
        change="added",
        path_abs=Path("/fake/a.py"),
        path_rel=Path("a.py"),
        is_dir=False,
        watch_name="w",
    )


class TestDispatcher:
    def test_sequential_dispatch(self, tmp_path: Path):
        config = _make_config(max_workers=1)
        dispatcher = Dispatcher(config, tmp_path)
        matched = [(config.rule[0], [_evt()])]
        results = dispatcher.dispatch(matched)
        assert len(results) == 2
        assert all(r.exit_code == 0 for r in results)

    def test_concurrent_dispatch(self, tmp_path: Path):
        config = _make_config(max_workers=2)
        dispatcher = Dispatcher(config, tmp_path)
        matched = [(config.rule[0], [_evt()])]
        results = dispatcher.dispatch(matched)
        assert len(results) == 2
        assert all(r.exit_code == 0 for r in results)

    def test_empty_matched(self, tmp_path: Path):
        config = _make_config()
        dispatcher = Dispatcher(config, tmp_path)
        results = dispatcher.dispatch([])
        assert results == []
