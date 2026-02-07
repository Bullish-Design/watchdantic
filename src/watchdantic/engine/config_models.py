"""Pydantic config models for watch.toml schema."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class EngineConfig(BaseModel):
    """Top-level [engine] section."""

    repo_root: str = "."
    debounce_ms: int = Field(default=300, ge=0)
    step_ms: int | None = Field(default=None, ge=0)
    use_default_filter: bool = True
    ignore_dirs: list[str] = Field(default_factory=lambda: [".git", ".venv", "__pycache__"])
    ignore_globs: list[str] = Field(default_factory=list)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    max_workers: int = Field(default=1, ge=1)


class WatchConfig(BaseModel):
    """A [[watch]] entry."""

    name: str
    paths: list[str] = Field(min_length=1)
    debounce_ms: int | None = Field(default=None, ge=0)
    use_default_filter: bool | None = None
    ignore_dirs: list[str] | None = None
    ignore_globs: list[str] | None = None

    @model_validator(mode="after")
    def _validate_paths(self) -> WatchConfig:
        for p in self.paths:
            normed = PurePosixPath(p)
            if ".." in normed.parts:
                raise ValueError(f"Watch path must not escape repo root: {p!r}")
        return self


class ActionConfig(BaseModel):
    """A [[action]] entry. Discriminated union by type (MVP: command only)."""

    name: str
    type: Literal["command"] = "command"
    cmd: list[str] = Field(min_length=1)
    cwd: str | None = None
    env: dict[str, str] | None = None
    timeout_s: int | None = Field(default=None, ge=1)
    shell: bool = False

    @model_validator(mode="after")
    def _validate_cwd(self) -> ActionConfig:
        if self.cwd is not None:
            normed = PurePosixPath(self.cwd)
            if ".." in normed.parts:
                raise ValueError(f"Action cwd must not escape repo root: {self.cwd!r}")
        return self


EventType = Literal["added", "modified", "deleted"]


class RuleConfig(BaseModel):
    """A [[rule]] entry."""

    name: str
    watch: str
    on: list[EventType] = Field(min_length=1)
    match: list[str] = Field(min_length=1)
    exclude: list[str] = Field(default_factory=list)
    do: list[str] = Field(min_length=1)
    continue_on_error: bool = False


class RepoConfig(BaseModel):
    """Root config object representing the entire watch.toml."""

    version: int = 1
    engine: EngineConfig = Field(default_factory=EngineConfig)
    watch: list[WatchConfig] = Field(default_factory=list)
    action: list[ActionConfig] = Field(default_factory=list)
    rule: list[RuleConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_cross_references(self) -> RepoConfig:
        # Uniqueness checks
        watch_names: dict[str, int] = {}
        for i, w in enumerate(self.watch):
            if w.name in watch_names:
                raise ValueError(f"Duplicate watch name: {w.name!r}")
            watch_names[w.name] = i

        action_names: dict[str, int] = {}
        for i, a in enumerate(self.action):
            if a.name in action_names:
                raise ValueError(f"Duplicate action name: {a.name!r}")
            action_names[a.name] = i

        rule_names: dict[str, int] = {}
        for i, r in enumerate(self.rule):
            if r.name in rule_names:
                raise ValueError(f"Duplicate rule name: {r.name!r}")
            rule_names[r.name] = i

        # Reference checks
        for r in self.rule:
            if r.watch not in watch_names:
                raise ValueError(
                    f"Rule {r.name!r} references unknown watch {r.watch!r}"
                )
            for action_name in r.do:
                if action_name not in action_names:
                    raise ValueError(
                        f"Rule {r.name!r} references unknown action {action_name!r}"
                    )

        # Path traversal on watch paths
        for w in self.watch:
            for p in w.paths:
                normed = PurePosixPath(p)
                if ".." in normed.parts:
                    raise ValueError(
                        f"Watch {w.name!r} path escapes repo root: {p!r}"
                    )

        return self

    def resolve_paths(self, config_dir: Path) -> Path:
        """Resolve repo_root to an absolute path. Returns the absolute repo root."""
        repo_root = (config_dir / self.engine.repo_root).resolve()
        return repo_root
