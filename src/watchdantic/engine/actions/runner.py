"""Action runner: dispatches actions by type."""

from __future__ import annotations

import logging
from pathlib import Path

from watchdantic.engine.actions.command import ActionResult, run_command
from watchdantic.engine.config_models import ActionConfig
from watchdantic.engine.events import FileEvent

logger = logging.getLogger("watchdantic.actions.runner")


def run_action(
    action: ActionConfig,
    events: list[FileEvent],
    rule_name: str,
    watch_name: str,
    repo_root: Path,
) -> ActionResult:
    """Run a single action. Dispatch by action.type for future extensibility."""
    if action.type == "command":
        return run_command(action, events, rule_name, watch_name, repo_root)
    else:
        raise ValueError(f"Unknown action type: {action.type!r}")


def run_rule_actions(
    actions: list[ActionConfig],
    events: list[FileEvent],
    rule_name: str,
    watch_name: str,
    repo_root: Path,
    continue_on_error: bool,
) -> list[ActionResult]:
    """Run all actions for a matched rule, respecting error policy."""
    results: list[ActionResult] = []
    for action in actions:
        result = run_action(action, events, rule_name, watch_name, repo_root)
        results.append(result)
        if result.exit_code != 0 and not continue_on_error:
            logger.warning(
                "Stopping rule %r actions due to failure in %r (exit %d)",
                rule_name,
                action.name,
                result.exit_code,
            )
            break
    return results
