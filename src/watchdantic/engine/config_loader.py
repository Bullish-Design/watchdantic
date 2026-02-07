"""Load and validate watch.toml configuration."""

from __future__ import annotations

import tomllib
from pathlib import Path

from watchdantic.exceptions import ConfigurationError
from watchdantic.engine.config_models import RepoConfig


def load_config(config_path: Path) -> RepoConfig:
    """Load watch.toml from the given path and return a validated RepoConfig.

    Raises ConfigurationError on any parsing or validation failure.
    """
    if not config_path.exists():
        raise ConfigurationError(f"Config file not found: {config_path}")

    try:
        raw = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigurationError(f"Cannot read config file: {exc}") from exc

    try:
        data = tomllib.loads(raw)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigurationError(f"Invalid TOML: {exc}") from exc

    try:
        config = RepoConfig.model_validate(data)
    except Exception as exc:
        raise ConfigurationError(f"Config validation error: {exc}") from exc

    return config


def find_config(start: Path | None = None) -> Path:
    """Search for watch.toml starting from `start` (default: cwd) upward."""
    current = (start or Path.cwd()).resolve()
    while True:
        candidate = current / "watch.toml"
        if candidate.is_file():
            return candidate
        parent = current.parent
        if parent == current:
            raise ConfigurationError(
                "No watch.toml found in current directory or any parent"
            )
        current = parent
