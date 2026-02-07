"""Tests for rule matching logic."""

from __future__ import annotations

from pathlib import Path

from watchdantic.engine.config_models import RuleConfig
from watchdantic.engine.events import FileEvent
from watchdantic.engine.matcher import event_matches_rule, match_events_to_rules


def _evt(change: str, rel: str, watch_name: str = "repo") -> FileEvent:
    """Helper to create a FileEvent for testing."""
    return FileEvent(
        change=change,
        path_abs=Path(f"/fake/{rel}"),
        path_rel=Path(rel),
        is_dir=False,
        watch_name=watch_name,
    )


def _rule(
    name: str = "r",
    watch: str = "repo",
    on: list[str] | None = None,
    match: list[str] | None = None,
    exclude: list[str] | None = None,
    do: list[str] | None = None,
) -> RuleConfig:
    return RuleConfig(
        name=name,
        watch=watch,
        on=on or ["added", "modified", "deleted"],
        match=match or ["**/*"],
        exclude=exclude or [],
        do=do or ["action1"],
    )


class TestEventMatchesRule:
    def test_basic_match(self):
        evt = _evt("added", "src/foo.py")
        rule = _rule(match=["src/**/*.py"])
        assert event_matches_rule(evt, rule) is True

    def test_event_type_filter(self):
        evt = _evt("deleted", "src/foo.py")
        rule = _rule(on=["added", "modified"], match=["**/*.py"])
        assert event_matches_rule(evt, rule) is False

    def test_watch_name_must_match(self):
        evt = _evt("added", "src/foo.py", watch_name="other")
        rule = _rule(watch="repo", match=["**/*.py"])
        assert event_matches_rule(evt, rule) is False

    def test_exclude_wins_over_match(self):
        evt = _evt("modified", "docs/_build/index.html")
        rule = _rule(match=["docs/**/*"], exclude=["docs/_build/**"])
        assert event_matches_rule(evt, rule) is False

    def test_no_match_returns_false(self):
        evt = _evt("added", "README.txt")
        rule = _rule(match=["**/*.py"])
        assert event_matches_rule(evt, rule) is False

    def test_glob_star_star(self):
        evt = _evt("modified", "a/b/c/d.md")
        rule = _rule(match=["**/*.md"])
        assert event_matches_rule(evt, rule) is True

    def test_single_dir_glob(self):
        evt = _evt("added", "docs/guide.md")
        rule = _rule(match=["docs/*.md"])
        assert event_matches_rule(evt, rule) is True

    def test_single_dir_glob_no_nested(self):
        evt = _evt("added", "docs/sub/guide.md")
        rule = _rule(match=["docs/*.md"])
        assert event_matches_rule(evt, rule) is False

    def test_recursive_glob_nested(self):
        evt = _evt("added", "docs/sub/deep/guide.md")
        rule = _rule(match=["docs/**/*.md"])
        assert event_matches_rule(evt, rule) is True

    def test_multiple_match_patterns_or(self):
        evt1 = _evt("added", "src/a.py")
        evt2 = _evt("added", "docs/b.md")
        rule = _rule(match=["**/*.py", "**/*.md"])
        assert event_matches_rule(evt1, rule) is True
        assert event_matches_rule(evt2, rule) is True

    def test_multiple_exclude_patterns_or(self):
        evt1 = _evt("added", "build/out.py")
        evt2 = _evt("added", "dist/out.py")
        rule = _rule(match=["**/*.py"], exclude=["build/**", "dist/**"])
        assert event_matches_rule(evt1, rule) is False
        assert event_matches_rule(evt2, rule) is False


class TestMatchEventsToRules:
    def test_basic_batch(self):
        events = [
            _evt("added", "src/a.py"),
            _evt("modified", "src/b.py"),
            _evt("deleted", "README.md"),
        ]
        rules = [
            _rule(name="py_rule", on=["added", "modified"], match=["**/*.py"]),
            _rule(name="md_rule", on=["deleted"], match=["**/*.md"]),
        ]
        matched = match_events_to_rules(events, rules)
        assert len(matched) == 2

        py_match = next(m for m in matched if m[0].name == "py_rule")
        assert len(py_match[1]) == 2

        md_match = next(m for m in matched if m[0].name == "md_rule")
        assert len(md_match[1]) == 1

    def test_no_matches(self):
        events = [_evt("added", "data.csv")]
        rules = [_rule(match=["**/*.py"])]
        assert match_events_to_rules(events, rules) == []

    def test_empty_events(self):
        rules = [_rule()]
        assert match_events_to_rules([], rules) == []

    def test_empty_rules(self):
        events = [_evt("added", "a.py")]
        assert match_events_to_rules(events, []) == []
