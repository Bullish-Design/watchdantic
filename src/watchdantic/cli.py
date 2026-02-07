"""CLI entry point for watchdantic."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
from pathlib import Path

from watchdantic.engine.config_loader import find_config, load_config
from watchdantic.engine.engine import Engine
from watchdantic.exceptions import ConfigurationError, WatchdanticError


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s [%(levelname)8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def cmd_run(args: argparse.Namespace) -> int:
    """Start the file watching engine."""
    config_path = Path(args.config) if args.config else find_config()
    config = load_config(config_path)
    _setup_logging(config.engine.log_level)

    logger = logging.getLogger("watchdantic.cli")
    repo_root = config.resolve_paths(config_path.parent)

    logger.info("Config: %s", config_path)
    logger.info("Repo root: %s", repo_root)
    logger.info(
        "Watches: %s",
        ", ".join(w.name for w in config.watch),
    )
    logger.info(
        "Rules: %s",
        ", ".join(r.name for r in config.rule),
    )

    pid_file = repo_root / ".watchdantic.pid"
    engine = Engine(config, repo_root)

    # On SIGHUP: reload config and restart
    def on_sighup(signum: int, frame: object) -> None:
        logger.info("SIGHUP received, reloading config")
        try:
            new_config = load_config(config_path)
            engine.reload_config(new_config)
        except WatchdanticError as exc:
            logger.error("Reload failed: %s", exc)

    signal.signal(signal.SIGHUP, on_sighup)

    try:
        engine.run_forever(pid_file=pid_file)
    except KeyboardInterrupt:
        logger.info("Shutting down")
    finally:
        engine.stop()
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Validate config and exit."""
    config_path = Path(args.config) if args.config else find_config()
    try:
        config = load_config(config_path)
    except ConfigurationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Config OK: {config_path}")
    print(f"  Version: {config.version}")
    print(f"  Watches: {len(config.watch)}")
    print(f"  Actions: {len(config.action)}")
    print(f"  Rules:   {len(config.rule)}")
    for w in config.watch:
        print(f"  Watch {w.name!r}: paths={w.paths}")
    for a in config.action:
        print(f"  Action {a.name!r}: type={a.type}")
    for r in config.rule:
        print(f"  Rule {r.name!r}: watch={r.watch} -> {r.do}")
    return 0


def cmd_reload(args: argparse.Namespace) -> int:
    """Send SIGHUP to a running watchdantic process to reload config."""
    pid_file = Path(args.pid_file) if args.pid_file else Path(".watchdantic.pid")

    if not pid_file.exists():
        print(f"ERROR: PID file not found: {pid_file}", file=sys.stderr)
        print("Is watchdantic running? (start with: watchdantic run)", file=sys.stderr)
        return 1

    try:
        pid = int(pid_file.read_text().strip())
    except (ValueError, OSError) as exc:
        print(f"ERROR: Cannot read PID file: {exc}", file=sys.stderr)
        return 1

    try:
        os.kill(pid, signal.SIGHUP)
    except ProcessLookupError:
        print(f"ERROR: Process {pid} not found. Stale PID file?", file=sys.stderr)
        pid_file.unlink(missing_ok=True)
        return 1
    except PermissionError:
        print(f"ERROR: Permission denied sending signal to PID {pid}", file=sys.stderr)
        return 1

    print(f"Sent SIGHUP to PID {pid} — config reload requested")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    """Generate a starter watch.toml."""
    output = Path(args.output) if args.output else Path("watch.toml")
    if output.exists() and not args.force:
        print(f"ERROR: {output} already exists. Use --force to overwrite.", file=sys.stderr)
        return 1

    template = '''\
version = 1

[engine]
repo_root = "."
debounce_ms = 300
use_default_filter = true
ignore_dirs = [".git", ".venv", "__pycache__"]
ignore_globs = ["**/*.pyc", "**/.DS_Store"]
log_level = "INFO"

[[watch]]
name = "repo"
paths = ["."]

[[action]]
name = "echo_change"
type = "command"
cmd = ["echo", "File changed!"]

[[rule]]
name = "notify_on_change"
watch = "repo"
on = ["added", "modified", "deleted"]
match = ["**/*"]
do = ["echo_change"]
'''
    output.write_text(template)
    print(f"Created {output}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="watchdantic",
        description="Config-driven file watcher with shell command actions",
    )
    parser.add_argument(
        "--version", action="version", version="watchdantic 0.2.0"
    )

    sub = parser.add_subparsers(dest="command")

    # run
    p_run = sub.add_parser("run", help="Start watching")
    p_run.add_argument("-c", "--config", help="Path to watch.toml")
    p_run.set_defaults(func=cmd_run)

    # check
    p_check = sub.add_parser("check", help="Validate config and exit")
    p_check.add_argument("-c", "--config", help="Path to watch.toml")
    p_check.set_defaults(func=cmd_check)

    # reload
    p_reload = sub.add_parser("reload", help="Reload config for running instance")
    p_reload.add_argument("--pid-file", help="Path to PID file (default: .watchdantic.pid)")
    p_reload.set_defaults(func=cmd_reload)

    # init
    p_init = sub.add_parser("init", help="Generate starter watch.toml")
    p_init.add_argument("-o", "--output", help="Output file (default: watch.toml)")
    p_init.add_argument("-f", "--force", action="store_true", help="Overwrite existing file")
    p_init.set_defaults(func=cmd_init)

    parsed = parser.parse_args(argv)
    if not hasattr(parsed, "func"):
        parser.print_help()
        return 1

    return parsed.func(parsed)


if __name__ == "__main__":
    sys.exit(main())
