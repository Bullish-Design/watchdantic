"""Core engine: runs watchfiles loops, normalizes events, dispatches actions."""

from __future__ import annotations

import logging
import os
import signal
import threading
from pathlib import Path

from watchfiles import Change, DefaultFilter, watch

from watchdantic.engine.config_models import RepoConfig, WatchConfig
from watchdantic.engine.dispatcher import Dispatcher
from watchdantic.engine.events import FileEvent, normalize_changes
from watchdantic.engine.matcher import _glob_match, match_events_to_rules

logger = logging.getLogger("watchdantic.engine")


class Engine:
    """Main file watching engine.

    Manages one watchfiles loop per [[watch]] block, normalizes events,
    matches rules, and dispatches actions.
    """

    def __init__(self, config: RepoConfig, repo_root: Path) -> None:
        self._config = config
        self._repo_root = repo_root
        self._dispatcher = Dispatcher(config, repo_root)
        self._stop_event = threading.Event()
        self._threads: list[threading.Thread] = []
        self._reload_event = threading.Event()
        self._pid_file: Path | None = None

    @property
    def config(self) -> RepoConfig:
        return self._config

    def reload_config(self, new_config: RepoConfig) -> None:
        """Hot-reload with a new config. Signals the engine to restart loops."""
        logger.info("Reloading engine configuration")
        self._config = new_config
        self._dispatcher = Dispatcher(new_config, self._repo_root)
        self._reload_event.set()

    def run_forever(self, pid_file: Path | None = None) -> None:
        """Run the engine until interrupted. Supports SIGHUP reload."""
        self._pid_file = pid_file
        if pid_file:
            pid_file.write_text(str(os.getpid()))
            logger.info("PID %d written to %s", os.getpid(), pid_file)

        # Install SIGHUP handler only from the main thread
        original_sighup = None
        is_main = threading.current_thread() is threading.main_thread()
        if is_main:
            original_sighup = signal.getsignal(signal.SIGHUP)
            signal.signal(signal.SIGHUP, self._handle_sighup)

        try:
            while not self._stop_event.is_set():
                self._reload_event.clear()
                logger.info("Starting watch loops")
                self._run_watch_loops()
                # If we get here due to reload, loop continues
                if self._reload_event.is_set():
                    logger.info("Reload triggered, restarting watch loops")
                    continue
                break
        except KeyboardInterrupt:
            logger.info("Interrupted, shutting down")
        finally:
            if is_main and original_sighup is not None:
                signal.signal(signal.SIGHUP, original_sighup)
            if pid_file and pid_file.exists():
                pid_file.unlink()
            self._stop_event.set()

    def run_once(self, timeout_s: float = 5.0) -> list[FileEvent]:
        """Process exactly one batch of changes and return events. For testing."""
        all_events: list[FileEvent] = []
        for watch_cfg in self._config.watch:
            watch_paths = self._resolve_watch_paths(watch_cfg)
            debounce_ms = watch_cfg.debounce_ms or self._config.engine.debounce_ms

            kwargs = self._build_watch_kwargs(watch_cfg, debounce_ms)

            for raw_changes in watch(
                *watch_paths,
                **kwargs,
            ):
                events = normalize_changes(raw_changes, self._repo_root, watch_cfg.name)
                events = self._apply_ignore_globs(events, watch_cfg)
                all_events.extend(events)

                if events:
                    matched = match_events_to_rules(events, self._config.rule)
                    if matched:
                        self._dispatcher.dispatch(matched)

                return all_events

        return all_events

    def stop(self) -> None:
        """Signal the engine to stop."""
        self._stop_event.set()
        self._reload_event.set()  # Unblock any waiting loop

    def _handle_sighup(self, signum: int, frame: object) -> None:
        """Handle SIGHUP for config reload."""
        logger.info("Received SIGHUP, triggering reload")
        self._reload_event.set()
        self._stop_event.set()  # Stop current loops so they restart

    def _run_watch_loops(self) -> None:
        """Start a watch thread per [[watch]] block and wait."""
        self._stop_event.clear()
        self._threads = []

        if len(self._config.watch) == 1:
            # Single watch: run in main thread
            self._watch_loop(self._config.watch[0])
        else:
            # Multiple watches: one thread each
            for watch_cfg in self._config.watch:
                t = threading.Thread(
                    target=self._watch_loop,
                    args=(watch_cfg,),
                    name=f"watch-{watch_cfg.name}",
                    daemon=True,
                )
                self._threads.append(t)
                t.start()

            # Wait for stop signal
            self._stop_event.wait()
            for t in self._threads:
                t.join(timeout=2.0)

    def _watch_loop(self, watch_cfg: WatchConfig) -> None:
        """Run a single watchfiles loop for one [[watch]] block."""
        watch_paths = self._resolve_watch_paths(watch_cfg)
        debounce_ms = watch_cfg.debounce_ms or self._config.engine.debounce_ms

        kwargs = self._build_watch_kwargs(watch_cfg, debounce_ms)

        logger.info(
            "Watching %r paths=%s debounce=%dms",
            watch_cfg.name,
            [str(p) for p in watch_paths],
            debounce_ms,
        )

        try:
            for raw_changes in watch(
                *watch_paths,
                stop_event=self._stop_event,
                **kwargs,
            ):
                events = normalize_changes(
                    raw_changes, self._repo_root, watch_cfg.name
                )
                events = self._apply_ignore_globs(events, watch_cfg)

                if not events:
                    continue

                logger.debug(
                    "Watch %r: %d events after filtering",
                    watch_cfg.name,
                    len(events),
                )

                matched = match_events_to_rules(events, self._config.rule)
                if matched:
                    self._dispatcher.dispatch(matched)
        except Exception:
            if not self._stop_event.is_set():
                logger.exception("Watch loop %r crashed", watch_cfg.name)

    def _resolve_watch_paths(self, watch_cfg: WatchConfig) -> list[Path]:
        """Resolve watch paths relative to repo root."""
        paths = []
        for p in watch_cfg.paths:
            resolved = (self._repo_root / p).resolve()
            paths.append(resolved)
        return paths

    def _build_watch_kwargs(self, watch_cfg: WatchConfig, debounce_ms: int) -> dict:
        """Build keyword args for watchfiles.watch()."""
        kwargs: dict = {
            "debounce": debounce_ms,
            "rust_timeout": 0,  # Use python stop_event
        }

        step_ms = self._config.engine.step_ms
        if step_ms is not None:
            kwargs["step"] = step_ms

        # Configure filter
        use_default = watch_cfg.use_default_filter
        if use_default is None:
            use_default = self._config.engine.use_default_filter

        if use_default:
            ignore_dirs = watch_cfg.ignore_dirs
            if ignore_dirs is None:
                ignore_dirs = self._config.engine.ignore_dirs
            # DefaultFilter supports ignore_dirs
            kwargs["watch_filter"] = DefaultFilter(
                ignore_dirs=ignore_dirs,
            )

        return kwargs

    def _apply_ignore_globs(
        self, events: list[FileEvent], watch_cfg: WatchConfig
    ) -> list[FileEvent]:
        """Filter events using ignore_globs from watch or engine config."""
        ignore_globs = watch_cfg.ignore_globs
        if ignore_globs is None:
            ignore_globs = self._config.engine.ignore_globs

        if not ignore_globs:
            return events

        filtered: list[FileEvent] = []
        for event in events:
            posix = event.path_rel_posix
            if not any(_glob_match(posix, pat) for pat in ignore_globs):
                filtered.append(event)
        return filtered
