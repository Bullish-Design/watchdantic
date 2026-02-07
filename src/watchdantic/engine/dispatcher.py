"""Central dispatcher: receives matched events and runs actions."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from watchdantic.engine.actions.command import ActionResult
from watchdantic.engine.actions.runner import run_rule_actions
from watchdantic.engine.config_models import ActionConfig, RepoConfig, RuleConfig
from watchdantic.engine.events import FileEvent

logger = logging.getLogger("watchdantic.dispatcher")


@dataclass
class Job:
    """A unit of work: a rule matched against events."""

    rule: RuleConfig
    events: list[FileEvent]
    actions: list[ActionConfig]


class Dispatcher:
    """Dispatches matched rules to the action runner.

    Supports sequential (max_workers=1) or concurrent execution.
    """

    def __init__(self, config: RepoConfig, repo_root: Path) -> None:
        self._config = config
        self._repo_root = repo_root
        self._action_map: dict[str, ActionConfig] = {
            a.name: a for a in config.action
        }
        self._max_workers = config.engine.max_workers

    def dispatch(
        self, matched: list[tuple[RuleConfig, list[FileEvent]]]
    ) -> list[ActionResult]:
        """Dispatch all matched rules to the action runner."""
        jobs = self._build_jobs(matched)
        if not jobs:
            return []

        if self._max_workers <= 1:
            return self._run_sequential(jobs)
        else:
            return self._run_concurrent(jobs)

    def _build_jobs(
        self, matched: list[tuple[RuleConfig, list[FileEvent]]]
    ) -> list[Job]:
        jobs: list[Job] = []
        for rule, events in matched:
            actions = [self._action_map[name] for name in rule.do]
            jobs.append(Job(rule=rule, events=events, actions=actions))
        return jobs

    def _run_sequential(self, jobs: list[Job]) -> list[ActionResult]:
        results: list[ActionResult] = []
        for job in jobs:
            logger.info(
                "Processing rule %r (%d events)",
                job.rule.name,
                len(job.events),
            )
            job_results = run_rule_actions(
                actions=job.actions,
                events=job.events,
                rule_name=job.rule.name,
                watch_name=job.rule.watch,
                repo_root=self._repo_root,
                continue_on_error=job.rule.continue_on_error,
            )
            results.extend(job_results)
        return results

    def _run_concurrent(self, jobs: list[Job]) -> list[ActionResult]:
        results: list[ActionResult] = []
        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            futures = []
            for job in jobs:
                logger.info(
                    "Submitting rule %r (%d events) to pool",
                    job.rule.name,
                    len(job.events),
                )
                fut = pool.submit(
                    run_rule_actions,
                    actions=job.actions,
                    events=job.events,
                    rule_name=job.rule.name,
                    watch_name=job.rule.watch,
                    repo_root=self._repo_root,
                    continue_on_error=job.rule.continue_on_error,
                )
                futures.append(fut)
            for fut in futures:
                results.extend(fut.result())
        return results
