"""Shell command action executor."""

from __future__ import annotations

import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from watchdantic.engine.config_models import ActionConfig
from watchdantic.engine.events import FileEvent, events_to_json
from watchdantic.exceptions import ActionError

logger = logging.getLogger("watchdantic.actions.command")


@dataclass(frozen=True, slots=True)
class ActionResult:
    """Result of a single action execution."""

    action_name: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    timed_out: bool = False


def build_env(
    action: ActionConfig,
    events: list[FileEvent],
    rule_name: str,
    watch_name: str,
    repo_root: Path,
) -> dict[str, str]:
    """Build environment variables for the subprocess."""
    env = os.environ.copy()
    # Watchdantic context vars
    env["WATCHDANTIC_REPO_ROOT"] = str(repo_root)
    env["WATCHDANTIC_RULE_NAME"] = rule_name
    env["WATCHDANTIC_WATCH_NAME"] = watch_name
    env["WATCHDANTIC_EVENT_COUNT"] = str(len(events))
    env["WATCHDANTIC_EVENTS_JSON"] = events_to_json(events)
    # User-specified env overrides
    if action.env:
        env.update(action.env)
    return env


def run_command(
    action: ActionConfig,
    events: list[FileEvent],
    rule_name: str,
    watch_name: str,
    repo_root: Path,
) -> ActionResult:
    """Execute a shell command action and return the result."""
    env = build_env(action, events, rule_name, watch_name, repo_root)

    cwd = str(repo_root / action.cwd) if action.cwd else str(repo_root)

    if action.shell:
        cmd = " ".join(action.cmd)
    else:
        cmd = action.cmd

    start = time.monotonic()
    timed_out = False
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=action.timeout_s,
            shell=action.shell,
            check=False,
        )
        exit_code = result.returncode
        stdout = result.stdout
        stderr = result.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = -1
        stdout = exc.stdout or "" if isinstance(exc.stdout, str) else (exc.stdout or b"").decode(errors="replace")
        stderr = exc.stderr or "" if isinstance(exc.stderr, str) else (exc.stderr or b"").decode(errors="replace")
    except OSError as exc:
        raise ActionError(f"Failed to execute action {action.name!r}: {exc}") from exc

    elapsed_ms = (time.monotonic() - start) * 1000

    action_result = ActionResult(
        action_name=action.name,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_ms=elapsed_ms,
        timed_out=timed_out,
    )

    if exit_code == 0:
        logger.info("Action %r completed in %.0fms", action.name, elapsed_ms)
    elif timed_out:
        logger.warning(
            "Action %r timed out after %ds", action.name, action.timeout_s
        )
    else:
        logger.warning(
            "Action %r exited with code %d (%.0fms)", action.name, exit_code, elapsed_ms
        )
        if stderr:
            logger.warning("  stderr: %s", stderr.strip())

    return action_result
