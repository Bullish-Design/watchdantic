from __future__ import annotations

import json
import logging
import sys
from fnmatch import fnmatch
from pathlib import Path
from typing import Callable, Dict, List, Optional, Type, Set, Any
from threading import Lock, Timer
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator, ConfigDict, PrivateAttr, ValidationError

from watchdantic.exceptions import ConfigurationError, FileFormatError
from watchdantic.formats.base import FileFormatBase


class WatchdanticConfig(BaseModel):
    """
    Global configuration for Watchdantic.

    This configuration model includes settings for debouncing, error handling,
    file processing limits, recursive prevention, and structured logging control.
    """

    # --- Core behavior ---
    debounce_seconds: float = Field(default=0.5, ge=0.0, description="Default debounce time in seconds")
    continue_on_error: bool = Field(default=False, description="Continue processing on validation errors")
    recursive: bool = Field(default=True, description="Watch subdirectories recursively")
    max_file_size_mb: int = Field(default=100, gt=0, description="Maximum file size in MB")
    default_debounce: float = Field(default=1.0, ge=0.0, description="Default debounce for recursive prevention")

    # --- Logging controls (Step 14) ---
    enable_logging: bool = Field(default=False, description="Enable structured JSONL logging (opt-in).")
    log_level: str = Field(
        default="INFO",
        description="Minimum log level for Watchdantic structured logs (e.g., DEBUG, INFO, WARNING, ERROR).",
    )
    log_file: Optional[Path] = Field(
        default=None, description="If provided, write JSONL logs to this file (append). If None, write to stdout."
    )

    model_config = ConfigDict(frozen=True)

    # -------------------------
    # Validators
    # -------------------------

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        candidate = str(v).upper().strip()
        valid = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        if candidate not in valid:
            # Be strict: fail fast to avoid silent misconfiguration
            raise ValueError(f"Invalid log_level '{v}'. Choose one of: {', '.join(sorted(valid))}")
        return candidate

    @field_validator("log_file")
    @classmethod
    def _normalize_log_file(cls, v: Optional[Path]) -> Optional[Path]:
        if v is None:
            return None
        # Expand and normalize
        p = Path(v).expanduser()
        # No existence requirement; file is created on write. If it exists and is a dir, error.
        if p.exists() and p.is_dir():
            raise ValueError(f"log_file points to a directory: {p}")
        return p

    # -------------------------
    # Convenience accessors
    # -------------------------

    @property
    def max_bytes(self) -> int:
        """Max file size in bytes, derived from max_file_size_mb."""
        return int(self.max_file_size_mb) * 1024 * 1024

    # -------------------------
    # Lifecycle hooks
    # -------------------------

    def model_post_init(self, __context: object) -> None:
        # Emit a concise debug record when configuration is created.
        logger = logging.getLogger("watchdantic")
        try:
            # Avoid logging secrets/paths excessively; this is a small, useful subset.
            logger.debug(
                "WatchdanticConfig initialized",
                extra={
                    "watchdantic": {
                        "debounce_seconds": self.debounce_seconds,
                        "continue_on_error": self.continue_on_error,
                        "recursive": self.recursive,
                        "max_file_size_mb": self.max_file_size_mb,
                        "default_debounce": self.default_debounce,
                        "enable_logging": self.enable_logging,
                        "log_level": self.log_level,
                        "log_file": str(self.log_file) if self.log_file else None,
                    }
                },
            )
        except Exception:
            # Never allow logging to disrupt normal operation
            logger.debug("WatchdanticConfig initialized (logging of extras failed safely)")


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


class DebounceManager(BaseModel):
    """
    Per-file debouncing with temporary exclusions and separated event/status API.

    Design:
    - `notify_file_event()` registers new filesystem events and (re)schedules timers
    - `is_file_ready()` checks and consumes ready state without affecting timers
    - `should_process_file()` provides backward compatibility by combining both operations
    - Temporary write-exclusion prevents processing during our own file operations
    - All shared structures are thread-safe with internal locking
    """

    # Active debounce timers per path
    pending_timers: Dict[Path, Timer] = Field(default_factory=dict)

    # Files currently excluded (e.g., following our own write operations)
    excluded_files: Set[Path] = Field(default_factory=set)

    # -------------------------
    # Private (non-Pydantic) attrs
    # -------------------------
    _ready_files: Set[Path] = PrivateAttr(default_factory=set)
    _lock: Lock = PrivateAttr(default_factory=Lock)

    model_config = dict(arbitrary_types_allowed=True)

    # -------------------------
    # Public API
    # -------------------------
    def notify_file_event(self, file_path: Path, debounce_seconds: float) -> None:
        """
        Notify of a new filesystem event for `file_path`.

        This will (re)schedule the debounce timer for the file, canceling any existing timer.
        If the file is temporarily excluded, this is a no-op.
        """
        with self._lock:
            if file_path not in self.excluded_files:
                self._schedule_timer(file_path, debounce_seconds)

    def is_file_ready(self, file_path: Path) -> bool:
        """
        Check if `file_path` is ready for processing.

        Returns True exactly once after a file's debounce timer has expired,
        consuming the ready state. Subsequent calls return False until the
        next timer expiration.
        """
        with self._lock:
            if file_path in self._ready_files:
                self._ready_files.remove(file_path)
                return True
            return False

    def exclude_file_temporarily(self, file_path: Path, duration: float) -> None:
        """
        Temporarily exclude a file from processing (e.g., for our own write operations).
        After `duration` seconds, the exclusion is automatically removed.
        """

        def _remove_exclusion() -> None:
            with self._lock:
                self.excluded_files.discard(file_path)

        with self._lock:
            self.excluded_files.add(file_path)
            t = Timer(duration, _remove_exclusion)
            t.daemon = True
            t.start()

    def is_file_excluded(self, file_path: Path) -> bool:
        """
        Check if a file is currently excluded from processing.

        Returns:
            True if the file is temporarily excluded, False otherwise
        """
        with self._lock:
            return file_path in self.excluded_files

    def cleanup_expired_timers(self) -> None:
        """
        Remove any dead/cancelled timers from `pending_timers` to avoid leaks.
        The timer callback already removes completed timers, so this primarily
        cleans up cancelled/dead ones.
        """
        with self._lock:
            dead: Set[Path] = set()
            for p, t in self.pending_timers.items():
                if not t.is_alive():
                    dead.add(p)
            for p in dead:
                self.pending_timers.pop(p, None)

    def clear_all(self) -> None:
        """Cancel all timers and clear all internal state (e.g., on shutdown)."""
        with self._lock:
            for t in self.pending_timers.values():
                try:
                    t.cancel()
                except Exception:
                    pass
            self.pending_timers.clear()
            self._ready_files.clear()
            self.excluded_files.clear()

    # -------------------------
    # Backward compatibility
    # -------------------------
    def should_process_file(self, file_path: Path, debounce_seconds: float) -> bool:
        """
        Backward-compatible method that combines notify_file_event and is_file_ready.

        This method:
        1. Notifies about the file event (scheduling/rescheduling timer)
        2. Immediately checks if the file is ready for processing

        For the new separated API, prefer using notify_file_event() and is_file_ready() separately.
        """
        if debounce_seconds == 0:
            return True
        self.notify_file_event(file_path, debounce_seconds)
        return self.is_file_ready(file_path)

    # -------------------------
    # Internal helpers
    # -------------------------
    def _schedule_timer(self, file_path: Path, debounce_seconds: float) -> None:
        """Cancel any existing timer for `file_path` and start a new one."""
        if (old := self.pending_timers.get(file_path)) is not None:
            try:
                old.cancel()
            except Exception:
                pass

        def _mark_ready() -> None:
            with self._lock:
                # Timer elapsed: mark ready and remove from active timers
                self._ready_files.add(file_path)
                self.pending_timers.pop(file_path, None)

        t = Timer(debounce_seconds, _mark_ready)
        t.daemon = True
        self.pending_timers[file_path] = t
        t.start()


class WatchdanticLogger(BaseModel):
    """
    Structured JSONL logger for Watchdantic.

    Behavior:
    - Only emits logs if config.enable_logging is True.
    - Respects config.log_level filtering.
    - Writes to config.log_file (append) or stdout when None.
    - Emits one JSON object per line to simplify downstream ingestion.

    JSON example:
    {
      "timestamp": "2025-01-15T10:00:00Z",
      "level": "INFO",
      "message": "File processed successfully",
      "file_path": "/path/to/file.jsonl",
      "handler_name": "process_logs",
      "model_count": 5
    }
    """

    # Provided by your existing models module
    config: "WatchdanticConfig"
    logger: logging.Logger = Field(default_factory=lambda: logging.getLogger("watchdantic.jsonl"))

    model_config = dict(arbitrary_types_allowed=True)

    def model_post_init(self, __context: Any) -> None:
        self._setup_logger()

    # -------------------------
    # Public logging API
    # -------------------------

    def log_event(self, level: str, message: str, **context: Any) -> None:
        """Emit a structured JSON line with arbitrary contextual fields."""
        if not getattr(self.config, "enable_logging", False):
            return

        lvl = self._level_to_int(level)
        if not self.logger.isEnabledFor(lvl):
            return

        payload = self._base_payload(level, message)
        payload.update(self._normalize_context(context))
        self._emit(payload, lvl)

    def log_file_processed(self, file_path: Path, handler_name: str, model_count: int) -> None:
        self.log_event(
            "INFO",
            "File processed successfully",
            file_path=str(file_path),
            handler_name=handler_name,
            model_count=int(model_count),
        )

    def log_validation_error(self, file_path: Path, error: ValidationError) -> None:
        self.log_event(
            "ERROR",
            "Validation error while parsing models",
            file_path=str(file_path),
            error_type="ValidationError",
            errors=error.errors(),
        )

    def log_format_error(self, file_path: Path, error: FileFormatError) -> None:
        self.log_event(
            "ERROR",
            "Format error while reading file",
            file_path=str(file_path),
            error_type=error.__class__.__name__,
            details=str(error),
        )

    # -------------------------
    # Internal helpers
    # -------------------------

    def _setup_logger(self) -> None:
        """Attach a handler and level only once; avoid duplicate handlers."""
        desired_level = self._level_to_int(getattr(self.config, "log_level", "INFO"))
        self.logger.setLevel(desired_level)

        target_is_file = getattr(self.config, "log_file", None) is not None
        target_path = Path(self.config.log_file) if target_is_file else None

        def _handler_matches(h: logging.Handler) -> bool:
            if target_is_file and isinstance(h, logging.FileHandler):
                try:
                    return Path(getattr(h, "baseFilename", "")) == target_path
                except Exception:
                    return False
            if not target_is_file and isinstance(h, logging.StreamHandler):
                return getattr(h, "stream", None) is sys.stdout
            return False

        existing = [h for h in self.logger.handlers if _handler_matches(h)]
        if existing:
            for h in existing:
                h.setLevel(desired_level)
        else:
            if target_is_file:
                handler: logging.Handler = logging.FileHandler(target_path, encoding="utf-8", mode="a")
            else:
                handler = logging.StreamHandler(stream=sys.stdout)
            handler.setLevel(desired_level)
            handler.setFormatter(logging.Formatter(fmt="%(message)s"))
            self.logger.addHandler(handler)

            if not any(isinstance(h, logging.NullHandler) for h in self.logger.handlers):
                self.logger.addHandler(logging.NullHandler())

        # Debug note that the logger was configured (no kwargs to _base_payload).
        payload = self._base_payload("DEBUG", "WatchdanticLogger configured")
        payload["destination"] = "file" if target_is_file else "stdout"
        try:
            self.logger.debug(json.dumps(payload))
        except Exception:
            # Never break on logging
            pass

    @staticmethod
    def _level_to_int(level: str) -> int:
        try:
            return getattr(logging, str(level).upper())
        except Exception:
            return logging.INFO

    @staticmethod
    def _utc_timestamp() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _base_payload(self, level: str, message: str) -> Dict[str, Any]:
        return {"timestamp": self._utc_timestamp(), "level": str(level).upper(), "message": message}

    @staticmethod
    def _normalize_context(ctx: Dict[str, Any]) -> Dict[str, Any]:
        normalized: Dict[str, Any] = {}
        for k, v in ctx.items():
            if isinstance(v, Path):
                normalized[k] = str(v)
            else:
                normalized[k] = v
        return normalized

    def _emit(self, payload: Dict[str, Any], level_int: int) -> None:
        try:
            line = json.dumps(payload, ensure_ascii=False)
        except TypeError:
            safe_payload = {k: (str(v) if not self._is_jsonable(v) else v) for k, v in payload.items()}
            line = json.dumps(safe_payload, ensure_ascii=False)
        self.logger.log(level_int, line)

    @staticmethod
    def _is_jsonable(value: Any) -> bool:
        try:
            json.dumps(value)
            return True
        except Exception:
            return False
