from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path
from typing import Callable, Dict, List, Optional, Type

from pydantic import BaseModel, Field, field_validator, ConfigDict

from ..exceptions import ConfigurationError
from ..formats.base import FileFormatBase


class HandlerInfo(BaseModel):
    """
    Immutable registration record describing how a handler should be invoked.

    Attributes:
        handler_func:
            The actual callable that will handle parsed models for a given file. The
            signature is: (models: List[BaseModel], file_path: Path) -> None.

        model_class:
            The Pydantic BaseModel subclass that parsed items will conform to.

        pattern:
            A glob-style match string (e.g. "*.jsonl", "data/**/*.json"). Must be non-empty.

        debounce:
            Debounce period (seconds) for this handler. Must be >= 0.

        continue_on_error:
            If True, errors inside this handler should be swallowed by the event processor
            (and logged) so other handlers can continue.

        recursive:
            If True, path matching is considered through subdirectories.

        exclude_patterns:
            Optional list of glob-style patterns that, if any match the file path,
            cause this handler to be skipped for that file.

        format_handler:
            Optional file format adapter responsible for reading/writing model payloads
            for the file extension (e.g. JsonLines/JsonSingle). If None, the system will
            auto-detect later based on file extension.
    """

    handler_func: Callable[[List[BaseModel], Path], None]
    model_class: Type[BaseModel]
    pattern: str = Field(..., description="Glob pattern used to match incoming paths")
    debounce: float = Field(0.5, description="Debounce in seconds (>= 0)")
    continue_on_error: bool = Field(False, description="Continue on error within handler")
    recursive: bool = Field(True, description="Whether subdirectories are considered")
    exclude_patterns: List[str] = Field(default_factory=list, description="Glob patterns to exclude")
    format_handler: Optional[FileFormatBase] = Field(default=None, description="Optional explicit format handler")

    # Allow non-Pydantic arbitrary types like FileFormatBase while keeping the model immutable.
    model_config = ConfigDict(
        frozen=True,
        arbitrary_types_allowed=True,
    )

    @field_validator("pattern")
    @classmethod
    def _validate_pattern(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ConfigurationError("HandlerInfo.pattern must be a non-empty string.")
        return v

    @field_validator("debounce")
    @classmethod
    def _validate_debounce(cls, v: float) -> float:
        try:
            fv = float(v)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError("HandlerInfo.debounce must be a number.") from exc
        if fv < 0:
            raise ConfigurationError("HandlerInfo.debounce must be >= 0.")
        return fv


class HandlerRegistry(BaseModel):
    """
    Mutable registry of handler definitions keyed by handler function name.

    Responsibilities:
        - Store HandlerInfo entries keyed by the handler function's __name__.
        - Register new handlers with conflict checks.
        - Provide efficient retrieval of handlers that apply to a given file path,
          honoring exclude_patterns.
    """

    handlers: Dict[str, HandlerInfo] = Field(default_factory=dict)

    # Explicitly *not* frozen for mutability (registration & clearing).
    model_config = ConfigDict(frozen=False)

    def register(self, handler_info: HandlerInfo) -> None:
        """
        Register a handler.

        Raises:
            ConfigurationError:
                - If a handler with the same function name is already registered.
                - If the handler function is not a callable.
        """
        func = handler_info.handler_func
        if not callable(func):
            raise ConfigurationError("handler_func must be callable.")

        name = getattr(func, "__name__", None)
        if not name or not isinstance(name, str):
            raise ConfigurationError("handler_func must have a valid __name__.")

        if name in self.handlers:
            raise ConfigurationError(f"Handler '{name}' is already registered.")

        self.handlers[name] = handler_info

    def get_handlers_for_path(self, file_path: Path) -> List[HandlerInfo]:
        """
        Return all handlers whose pattern matches the given file path and are not excluded.

        Matching:
            - For simple patterns (no path separators), matches against filename only
            - For complex patterns (with path separators), matches against full POSIX path
            - If any exclude pattern matches, that handler is omitted.

        Args:
            file_path: The path of the file that generated a filesystem event.

        Returns:
            A list of matching HandlerInfo instances (possibly empty).
        """
        path_str = file_path.as_posix()
        filename = file_path.name

        results: List[HandlerInfo] = []
        for info in self.handlers.values():
            # Determine match target based on pattern complexity
            pattern = info.pattern
            if "/" in pattern or "\\" in pattern:
                # Complex pattern with path separators - match against full path
                match_target = path_str
            else:
                # Simple pattern - match against filename only
                match_target = filename

            # Exclusions first (always check against full path for exclusions)
            if any(fnmatch(path_str, ex_pat) for ex_pat in info.exclude_patterns):
                continue

            # Positive match
            if fnmatch(match_target, pattern):
                results.append(info)

        return results

    def get_handler_names(self) -> List[str]:
        """Return a list of registered handler function names."""
        return list(self.handlers.keys())

    def clear(self) -> None:
        """Remove all registered handlers."""
        self.handlers.clear()
