# src/watchdantic/core/watcher.py
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Callable, List, Optional, Sequence, Type, Union, get_args, get_origin
import inspect
import logging
import typing
import threading

from watchdog.events import FileSystemEventHandler, FileSystemEvent
from watchdog.observers import Observer

from pydantic import BaseModel, ValidationError, PrivateAttr

# Project imports (no fallbacks/kludges)
from ..exceptions import ConfigurationError, FileFormatError
from ..formats.base import FileFormatBase
from ..formats.jsonlines import JsonLines
from ..formats.jsonsingle import JsonSingle
from .models import WatchdanticConfig, HandlerRegistry, HandlerInfo, DebounceManager, WatchdanticLogger


logger = logging.getLogger("watchdantic")


class FileEventProcessor(BaseModel):
    """Core engine to process filesystem events into handler executions.

    Focuses on:
      - reading files
      - auto-detecting format
      - parsing into Pydantic models
      - invoking registered handlers
      - structured logging via WatchdanticLogger
    """

    registry: HandlerRegistry
    config: WatchdanticConfig
    debounce: DebounceManager
    _jsonl: JsonLines = JsonLines()
    _json: JsonSingle = JsonSingle()
    _structured: WatchdanticLogger | None = None

    model_config = dict(arbitrary_types_allowed=True)

    def model_post_init(self, __context: Any) -> None:
        self._structured = WatchdanticLogger(config=self.config)
        logger.debug("FileEventProcessor initialized with structured logging=%s", self.config.enable_logging)

    # -------------------------
    # Public API
    # -------------------------
    def _schedule_processing(self, file_path: Path, handler: HandlerInfo) -> None:
        """Schedule file processing after debounce period."""

        def process_after_debounce():
            # Check if file is still ready after debounce
            if self.debounce.is_file_ready(file_path):
                try:
                    if not self._check_size(file_path, handler):
                        self._log_event(
                            "WARNING",
                            "File exceeds size limit; skipping",
                            file_path=file_path,
                            max_bytes=self.config.max_bytes,
                        )
                        return

                    models = self._read_models(file_path, handler.model_class)
                    logger.debug("Invoking handler %s for %s", handler.handler_func.__name__, file_path)
                    handler.handler_func(models, file_path)
                    self._log_file_processed(file_path, handler.handler_func.__name__, len(models))
                except FileFormatError as e:
                    logger.exception("Format error while reading %s", file_path)
                    self._log_format_error(file_path, e)
                except ValidationError as e:
                    logger.exception("Validation error while parsing %s", file_path)
                    self._log_validation_error(file_path, e)
                except Exception:
                    logger.exception("Handler %s raised for %s", handler.handler_func.__name__, file_path)
                    if not handler.continue_on_error:
                        raise

        # Schedule the processing after the debounce period
        timer = threading.Timer(handler.debounce, process_after_debounce)
        timer.daemon = True
        timer.start()

    # Update the process_event method
    def process_event(self, file_path: Path) -> None:
        """Handle a file system event for a given file path."""
        logger.info("Processing event for %s", file_path)
        matching_handlers = self._matching_handlers(file_path)
        if not matching_handlers:
            logger.debug("No handlers matched for %s", file_path)
            return

        for handler in matching_handlers:
            # Notify about the event and schedule processing
            self.debounce.notify_file_event(file_path, handler.debounce)
            self._schedule_processing(file_path, handler)

    # -------------------------
    # Internals
    # -------------------------

    def _matching_handlers(self, file_path: Path) -> List[HandlerInfo]:
        return self.registry.get_handlers_for_path(file_path)

    def _check_size(self, file_path: Path, h: HandlerInfo) -> bool:
        try:
            size = file_path.stat().st_size
        except FileNotFoundError:
            logger.warning("File disappeared before read: %s", file_path)
            return False
        max_bytes = getattr(self.config, "max_bytes", 100 * 1024 * 1024)
        ok = size <= max_bytes
        logger.debug("Size check for %s: %s (max=%s)", file_path, ok, max_bytes)
        return ok

    def _detect_format(self, file_path: Path) -> FileFormatBase:
        suffix = file_path.suffix.lower()
        if suffix == ".jsonl":
            return self._jsonl
        if suffix == ".json":
            return self._json
        raise FileFormatError(f"Unsupported file extension: {suffix}")

    def _read_models(self, file_path: Path, model_type: Type[BaseModel]) -> List[BaseModel]:
        fmt = self._detect_format(file_path)
        logger.debug("Detected format %s for %s", fmt.__class__.__name__, file_path)
        models = fmt.read_models(file_path, model_type)  # Pass model_type
        logger.info("Read %d models from %s", len(models), file_path)
        return models

    # -------------------------
    # Structured logging helpers
    # -------------------------

    def _log_event(self, level: str, message: str, **ctx: Any) -> None:
        if self._structured:
            self._structured.log_event(level, message, **ctx)

    def _log_file_processed(self, file_path: Path, handler_name: str, model_count: int) -> None:
        if self._structured:
            self._structured.log_file_processed(file_path, handler_name, model_count)

    def _log_validation_error(self, file_path: Path, error: ValidationError) -> None:
        if self._structured:
            self._structured.log_validation_error(file_path, error)

    def _log_format_error(self, file_path: Path, error: FileFormatError) -> None:
        if self._structured:
            self._structured.log_format_error(file_path, error)


class WatchdanticCore:
    """Core watcher object exposing the @triggers_on decorator and write operations.

    This class owns the handler registry and debounce manager. Higher-level orchestration
    (observer wiring, event loop, etc.) is handled in later steps.
    """

    def __init__(
        self,
        config: Optional[WatchdanticConfig] = None,
        registry: Optional[HandlerRegistry] = None,
        debounce_manager: Optional[DebounceManager] = None,
    ) -> None:
        self.config = config or WatchdanticConfig()
        self.registry = registry or HandlerRegistry()
        self.debounce_manager = debounce_manager or DebounceManager()

    # ------------------------------ Decorator API ------------------------------
    def triggers_on(
        self,
        model_class: Type[BaseModel],
        pattern: str,
        debounce: float = 1.0,
        continue_on_error: bool = False,
        recursive: bool = True,
        exclude_patterns: Optional[List[str]] = None,
        format: Optional[FileFormatBase] = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator to register handlers for file changes.

        The handler function must accept `(models: List[model_class], file_path: Path)` and return `None`.
        """

        # --- Parameter validation (fail fast) ---
        if not isinstance(pattern, str) or not pattern.strip():
            raise ConfigurationError("pattern must be a non-empty string")

        if not inspect.isclass(model_class) or not issubclass(model_class, BaseModel):
            raise ConfigurationError("model_class must be a subclass of pydantic.BaseModel")

        if not isinstance(debounce, (int, float)) or debounce < 0:
            raise ConfigurationError("debounce must be a non-negative number")

        if exclude_patterns is None:
            exclude_patterns = []
        else:
            if not isinstance(exclude_patterns, list) or not all(isinstance(p, str) for p in exclude_patterns):
                raise ConfigurationError("exclude_patterns must be a list[str] if provided")

        if format is not None and not isinstance(format, FileFormatBase):
            raise ConfigurationError("format must be a FileFormatBase instance or None")

        # Auto-detect format from pattern if not explicitly provided
        fmt = format or self._infer_format(pattern)

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            # Validate handler signature strictly before registration
            self._validate_handler_signature(func, model_class)

            info = HandlerInfo(
                handler_func=func,
                model_class=model_class,
                pattern=pattern,
                debounce=float(debounce),
                continue_on_error=bool(continue_on_error),
                recursive=bool(recursive),
                exclude_patterns=list(exclude_patterns),
                format_handler=fmt,
            )

            # Register with the registry (Step 7 integration)
            if hasattr(self.registry, "register"):
                self.registry.register(info)  # type: ignore[misc]
            else:
                # Minimal fallback if registry lacks a register() method
                handlers = getattr(self.registry, "handlers")  # type: ignore[attr-defined]
                if isinstance(handlers, dict):
                    handlers[func.__name__] = info
                elif isinstance(handlers, list):
                    handlers.append(info)

            return func

        return decorator

    # ------------------------------ Write Operations ------------------------------
    def write_models(self, models: List[BaseModel], file_path: Union[str, Path]) -> None:
        """Write a list of models to a file with automatic format detection and atomic writes.

        This method includes recursive prevention - the target file will be temporarily excluded
        from processing to prevent handlers from triggering themselves.

        Args:
            models: List of Pydantic model instances to write
            file_path: Target file path (as string or Path object)

        Raises:
            FileFormatError: If serialization or file operations fail
        """
        target_path = Path(file_path) if isinstance(file_path, str) else file_path

        logger.info(f"Writing {len(models)} models to {target_path}")

        # STEP 13: Recursive prevention - exclude file temporarily before writing
        exclusion_duration = self.config.default_debounce if hasattr(self.config, "default_debounce") else 1.0
        self.debounce_manager.exclude_file_temporarily(target_path, exclusion_duration)
        logger.debug(f"Temporarily excluded {target_path} from processing for {exclusion_duration}s")

        # Create parent directories if they don't exist
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Auto-detect format from file extension
        format_handler = self._detect_format_for_path(target_path)
        logger.debug(f"Using format handler: {type(format_handler).__name__}")

        try:
            # Generate content using format handler
            content = format_handler.write(models)
            logger.debug(f"Generated {len(content)} characters of content")
        except Exception as exc:
            raise FileFormatError(f"Failed to serialize models for {target_path}: {exc}") from exc

        # Perform atomic write
        self._atomic_write(target_path, content)
        logger.info(f"Successfully wrote {len(models)} models to {target_path} with recursive prevention")

    def _detect_format_for_path(self, file_path: Path) -> FileFormatBase:
        """Detect file format handler based on file extension."""
        suffix = file_path.suffix.lower()
        if suffix in (".jsonl", ".jsonlines"):
            return JsonLines()
        if suffix == ".json":
            return JsonSingle()
        # Default to JsonLines for unknown extensions
        logger.debug(f"Unknown extension {suffix}, defaulting to JsonLines")
        return JsonLines()

    def _atomic_write(self, target_path: Path, content: str) -> None:
        """Perform atomic write using temporary file and rename.

        This prevents partial file states during write operations.
        """
        logger.debug(f"Starting atomic write to {target_path}")

        # Create temporary file in the same directory as target
        temp_fd = None
        temp_path = None

        try:
            # Create temporary file in same directory to ensure atomic rename
            temp_fd, temp_path_str = tempfile.mkstemp(
                dir=target_path.parent, prefix=f".{target_path.name}.", suffix=".tmp"
            )
            temp_path = Path(temp_path_str)
            logger.debug(f"Created temporary file: {temp_path}")

            # Write content to temporary file
            with os.fdopen(temp_fd, "w", encoding="utf-8") as temp_file:
                temp_file.write(content)
                temp_file.flush()
                os.fsync(temp_file.fileno())  # Ensure data is written to disk
            temp_fd = None  # File descriptor is now closed

            # Atomic rename (on most filesystems)
            temp_path.replace(target_path)
            logger.debug(f"Atomically renamed {temp_path} to {target_path}")
            temp_path = None  # Successfully renamed, no cleanup needed

        except Exception as exc:
            logger.error(f"Atomic write failed for {target_path}: {exc}")
            raise FileFormatError(f"Failed to write file {target_path}: {exc}") from exc

        finally:
            # Cleanup on failure
            if temp_fd is not None:
                try:
                    os.close(temp_fd)
                except OSError:
                    pass
            if temp_path is not None and temp_path.exists():
                try:
                    temp_path.unlink()
                    logger.debug(f"Cleaned up temporary file: {temp_path}")
                except OSError:
                    logger.warning(f"Failed to cleanup temporary file: {temp_path}")

    # ------------------------------ Helpers ------------------------------
    @staticmethod
    def _infer_format(pattern: str) -> Optional[FileFormatBase]:
        """Infer a file format handler by common extensions.

        - \"*.jsonl\" / \".jsonl\" -> JsonLines
        - \"*.json\" / \".json\"   -> JsonSingle
        Unknown extensions return None (caller may rely on runtime detection).
        """
        lower = pattern.lower()
        if lower.endswith(".jsonl"):
            return JsonLines()
        if lower.endswith(".json"):
            return JsonSingle()
        return None

    @staticmethod
    def _validate_handler_signature(func: Callable[..., Any], model_class: Type[BaseModel]) -> None:
        sig = inspect.signature(func)
        logger.info("Validating handler signature for %s: %s", func.__name__, sig)
        params = list(sig.parameters.values())
        logger.info(f"  Parameters: {params}")

        if len(params) != 2:
            raise ConfigurationError(
                "handler must accept exactly two parameters: (models: List[Model], file_path: Path)"
            )

        models_param, path_param = params[0], params[1]

        # Get the actual type hints, resolving string annotations
        try:
            type_hints = typing.get_type_hints(func)
            logger.info(f"  Resolved type hints: {type_hints}")
        except (NameError, AttributeError) as e:
            # If we can't resolve type hints, fall back to checking the string representation
            ann = models_param.annotation
            logger.info(f"  Unable to resolve type hints, using raw annotation: {ann}")
            if isinstance(ann, str):
                expected_annotation = f"List[{model_class.__name__}]"
                if ann != expected_annotation:
                    raise ConfigurationError(
                        f"first parameter must be annotated as List[{model_class.__name__}] "
                        f"matching the decorator's model_class. Got: {ann}"
                    )
                # Also check second param
                path_ann = path_param.annotation
                if path_ann != "Path":
                    raise ConfigurationError("second parameter must be annotated as pathlib.Path")
                return
            else:
                raise ConfigurationError(f"Unable to resolve type hints: {e}")

        # Validate first param annotation is List[model_class] or list[model_class]
        models_type = type_hints.get(models_param.name)
        logger.info(f"  models_param type: {models_type}")
        if models_type is None:
            raise ConfigurationError("first parameter must be annotated as List[Model] (missing annotation)")

        origin = get_origin(models_type)
        args = get_args(models_type)
        logger.info(f"  origin: {origin}, args: {args}")
        # Handle both typing.List and built-in list
        is_list = origin in (list, List) or (
            hasattr(models_type, "__origin__") and models_type.__origin__ in (list, List)
        )
        logger.info(f"    Is list? {is_list}")
        # Model class checking
        correct_model = len(args) == 1 and args[0] == model_class
        logger.info(f"  Correct Model: {correct_model}")
        if not (is_list and correct_model):
            raise ConfigurationError(
                f"first parameter must be annotated as List[{model_class.__name__}] "
                f"matching the decorator's model_class. Got: {models_type}"
            )

        # Validate second param is annotated Path
        path_type = type_hints.get(path_param.name)
        logger.info(f"  Validating second param is Path: {path_type}")
        if path_type is not Path:
            raise ConfigurationError("second parameter must be annotated as pathlib.Path")

        # Validate return type (allow None or no annotation)
        ret = type_hints.get("return")

        logger.info(f"  Return type validation: {ret}")
        if ret not in (inspect._empty, type(None), None):
            # if ret not in (inspect._empty, type(None)):
            raise ConfigurationError("handler must return None")


def _is_temp_or_hidden(path: Path) -> bool:
    name = path.name
    if name.startswith(".") and not name.lower().endswith((".json", ".jsonl")):
        return True
    if name.endswith((".swp", ".swx", "~", ".tmp", ".temp", ".partial")):
        return True
    # Common atomic-write patterns: tmp file in same folder
    if name.startswith((".tmp", "tmp", ".goutputstream")):
        return True
    return False


class _DispatchingHandler(FileSystemEventHandler):
    """Watchdog event handler that filters and delegates to FileEventProcessor."""

    def __init__(self, processor: FileEventProcessor, registry: HandlerRegistry, config: WatchdanticConfig) -> None:
        super().__init__()
        self._processor = processor
        self._registry = registry
        self._config = config

    # Created + modified are enough for our use case
    def on_created(self, event: FileSystemEvent) -> None:  # pragma: no cover - covered by on_modified path
        self._maybe_process(event)

    def on_modified(self, event: FileSystemEvent) -> None:
        self._maybe_process(event)

    def _maybe_process(self, event: FileSystemEvent) -> None:
        try:
            if getattr(event, "is_directory", False):
                return
            path = Path(getattr(event, "src_path", ""))
            if not path:
                return
            if _is_temp_or_hidden(path):
                logger.debug("Skipping temp/hidden file: %s", path)
                return

            # Only proceed if any handler matches
            # Change from matching() to get_handlers_for_path()
            matches = self._registry.get_handlers_for_path(path)  # Fixed method name
            if not matches:
                logger.debug("No handlers match: %s", path)
                return

            logger.debug("Dispatching %s to %d handler(s)", path, len(matches))
            self._processor.process_event(path)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Unhandled exception in file event processing for %s: %s", event, exc)


class Watchdantic(BaseModel):
    config: WatchdanticConfig = WatchdanticConfig()
    registry: HandlerRegistry = HandlerRegistry()
    # Remove debounce from public fields
    # debounce: DebounceManager = DebounceManager()  # Remove this line

    # Runtime attributes (not part of the model state)
    _observer: Optional[Observer] = PrivateAttr()
    _processor: Optional[FileEventProcessor] = PrivateAttr()
    _running_lock: threading.Lock = PrivateAttr()
    _debounce: DebounceManager = PrivateAttr()  # Add this line

    def __init__(self, config: Optional[WatchdanticConfig] = None) -> None:
        super().__init__()
        if config is not None:
            self.config = config
        logging.getLogger("watchdantic").setLevel(getattr(logging, self.config.log_level, logging.INFO))
        self._observer = None
        self._processor = None
        self._running_lock = threading.Lock()
        self._debounce = DebounceManager()  # Initialize here
        logger.debug("Watchdantic initialized with config: %s", self.config)

    # ---- Registration decorator -------------------------------------------------
    def triggers_on(
        self,
        model_class: Type[BaseModel],
        pattern: str,
        *,
        debounce: Optional[float] = None,
        continue_on_error: Optional[bool] = None,
        recursive: bool = True,
        exclude: Optional[Sequence[str]] = None,
        format_handler: Optional[FileFormatBase] = None,
    ) -> Callable[[Callable[[List[BaseModel], Path], Any]], Callable[[List[BaseModel], Path], Any]]:
        """Register a handler for filesystem events matching *pattern*.

        The handler signature must be (models: List[model_class], file_path: Path).
        """

        def decorator(func: Callable[[List[BaseModel], Path], Any]) -> Callable[[List[BaseModel], Path], Any]:
            hi = HandlerInfo(
                handler_func=func,
                model_class=model_class,
                pattern=pattern,
                debounce=self.config.debounce_seconds if debounce is None else debounce,
                continue_on_error=self.config.continue_on_error if continue_on_error is None else continue_on_error,
                recursive=recursive,
                exclude_patterns=list(exclude) if exclude else [],
                format_handler=format_handler,
            )
            logger.debug("Registering handler: %s", hi)
            self.registry.register(hi)
            return func

        return decorator

    # ---- Lifecycle --------------------------------------------------------------
    def start(self, path: Union[str, Path]) -> None:
        """Start watching *path* in a non-blocking way."""
        path = Path(path)
        logger.info("Starting Watchdantic observer on: %s", path)

        with self._running_lock:
            if self._observer is not None:
                logger.debug("Observer already running; ignoring start request")
                return

            # Build processor tied to our registry and debounce
            processor = FileEventProcessor(registry=self.registry, config=self.config, debounce=self._debounce)
            # processor = FileEventProcessor(registry=self.registry, config=self.config, debounce=self.debounce)
            handler = _DispatchingHandler(processor, self.registry, self.config)
            observer = Observer()

            # Decide recursion: if any handler wants recursion, we enable it. Safer superset.
            recursive = (
                any(h.recursive for h in self.registry.handlers.values())
                if getattr(self.registry, "handlers", None)
                else True
            )
            observer.schedule(handler, str(path), recursive=recursive)
            observer.start()

            self._processor = processor
            self._observer = observer
            logger.info("Watchdantic observer started (recursive=%s)", recursive)

    def stop(self) -> None:
        """Stop watching and clean up threads."""
        with self._running_lock:
            obs = self._observer
            if not obs:
                logger.debug("Observer not running; nothing to stop")
                return
            logger.info("Stopping Watchdantic observer")
            try:
                obs.stop()
                obs.join(timeout=5.0)
            finally:
                self._observer = None
                self._processor = None
            logger.info("Watchdantic observer stopped")
