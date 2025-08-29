from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Callable, List, Optional, Type, Union, get_args, get_origin
import inspect
import logging
import typing
import threading

from watchdog.events import FileSystemEventHandler, FileSystemEvent
from watchdog.observers import Observer

from pydantic import BaseModel, ValidationError, PrivateAttr

# Project imports
from ..exceptions import ConfigurationError, FileFormatError
from ..formats.base import FileFormatBase
from ..formats.detection import FormatDetector
from .config import WatchdanticConfig
from .handlers import HandlerRegistry, HandlerInfo
from .debouncing import DebounceManager
from .logging import WatchdanticLogger


logger = logging.getLogger("watchdantic")


class FileEventProcessor(BaseModel):
    """Core engine to process filesystem events into handler executions."""

    registry: HandlerRegistry
    config: WatchdanticConfig
    debounce: DebounceManager
    _format_detector: FormatDetector = FormatDetector()
    _structured: WatchdanticLogger | None = None

    model_config = dict(arbitrary_types_allowed=True)

    def model_post_init(self, __context: Any) -> None:
        self._structured = WatchdanticLogger(config=self.config)
        logger.debug("FileEventProcessor initialized with structured logging=%s", self.config.enable_logging)

    def process_event(self, file_path: Path) -> None:
        """Handle a file system event by scheduling debounced processing."""
        matching_handlers = self._matching_handlers(file_path)
        if not matching_handlers:
            logger.debug("No handlers matched for %s", file_path)
            return

        # Use the longest debounce period among all matching handlers for the file
        debounce_period = max(h.debounce for h in matching_handlers)
        logger.debug("Scheduling processing for %s in %ss", file_path, debounce_period)

        # Schedule the actual processing to happen after the debounce period
        self.debounce.schedule_processing(
            file_path,
            debounce_period,
            lambda: self._execute_handlers_for_path(file_path),
        )

    def _execute_handlers_for_path(self, file_path: Path) -> None:
        """Executes all matching handlers for a given file path."""
        # Re-fetch handlers at execution time to ensure they are current
        handlers = self._matching_handlers(file_path)
        if not handlers:
            logger.debug("No handlers matched %s at execution time", file_path)
            return

        logger.info("Executing %d handler(s) for %s", len(handlers), file_path)
        for handler in handlers:
            self._execute_handler(file_path, handler)

    def _execute_handler(self, file_path: Path, handler: HandlerInfo) -> None:
        """Process a file immediately with a single given handler."""
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

    def _read_models(self, file_path: Path, model_type: Type[BaseModel]) -> List[BaseModel]:
        fmt = self._format_detector.detect_format(file_path)
        logger.debug("Detected format %s for %s", fmt.__class__.__name__, file_path)
        models = fmt.read_models(file_path, model_type)
        logger.info("Read %d models from %s", len(models), file_path)
        return models

    # Structured logging helpers
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

    def on_created(self, event: FileSystemEvent) -> None:
        self._maybe_process(event)

    def on_modified(self, event: FileSystemEvent) -> None:
        self._maybe_process(event)

    def _maybe_process(self, event: FileSystemEvent) -> None:
        try:
            if getattr(event, "is_directory", False):
                return
            path = Path(getattr(event, "src_path", ""))
            if not path or _is_temp_or_hidden(path):
                return

            matches = self._registry.get_handlers_for_path(path)
            if matches:
                logger.debug("Dispatching %s to %d handler(s)", path, len(matches))
                self._processor.process_event(path)

        except Exception as exc:
            logger.exception("Unhandled exception processing %s: %s", event, exc)


class Watchdantic(BaseModel):
    config: WatchdanticConfig = WatchdanticConfig()
    registry: HandlerRegistry = HandlerRegistry()

    # Runtime attributes (not part of the model state)
    _observer: Optional[Observer] = PrivateAttr()
    _processor: Optional[FileEventProcessor] = PrivateAttr()
    _running_lock: threading.Lock = PrivateAttr()
    _debounce: DebounceManager = PrivateAttr()
    _format_detector: FormatDetector = PrivateAttr()

    def __init__(self, config: Optional[WatchdanticConfig] = None) -> None:
        """Initialize Watchdantic with optional configuration."""
        super().__init__()
        if config is not None:
            self.config = config

        # Use consistent attribute access
        log_level = getattr(logging, self.config.log_level, logging.INFO)
        logging.getLogger("watchdantic").setLevel(log_level)

        self._observer = None
        self._processor = None
        self._running_lock = threading.Lock()
        self._debounce = DebounceManager()
        self._format_detector = FormatDetector()
        logger.debug("Watchdantic initialized")

    def triggers_on(
        self,
        model_class: Type[BaseModel],
        pattern: str,
        *,
        debounce: Optional[float] = None,
        continue_on_error: Optional[bool] = None,
        recursive: bool = True,
        exclude_patterns: Optional[List[str]] = None,
        format_handler: Optional[FileFormatBase] = None,
    ) -> Callable[[Callable[[List[BaseModel], Path], Any]], Callable[[List[BaseModel], Path], Any]]:
        """
        Register a handler for filesystem events matching the specified pattern.

        Args:
            model_class: Pydantic model class for validation
            pattern: Glob pattern for file matching (e.g., '*.jsonl', 'data/**/*.json')
            debounce: Debounce time in seconds (uses config default if None)
            continue_on_error: Continue processing other files on validation errors
            recursive: Watch subdirectories recursively
            exclude_patterns: List of glob patterns to exclude from processing
            format_handler: Explicit format handler (auto-detected if None)

        Returns:
            Decorator function that registers the handler

        Raises:
            ConfigurationError: If handler signature or parameters are invalid
        """

        def decorator(func: Callable[[List[BaseModel], Path], Any]) -> Callable[[List[BaseModel], Path], Any]:
            # Validate handler signature
            self._validate_handler_signature(func, model_class)

            hi = HandlerInfo(
                handler_func=func,
                model_class=model_class,
                pattern=pattern,
                debounce=self.config.default_debounce if debounce is None else debounce,
                continue_on_error=self.config.continue_on_error if continue_on_error is None else continue_on_error,
                recursive=recursive,
                exclude_patterns=exclude_patterns or [],
                format_handler=format_handler,
            )
            logger.debug("Registering handler: %s for pattern: %s", func.__name__, pattern)
            self.registry.register(hi)
            return func

        return decorator

    def write_models(self, models: List[BaseModel], file_path: Union[str, Path]) -> None:
        """
        Write a list of models to a file with automatic format detection and atomic writes.
        This method includes recursive prevention - the target file will be temporarily excluded
        from processing to prevent handlers from triggering themselves.
        Args:
            models: List of Pydantic model instances to write
            file_path: Target file path (as string or Path object)

        Raises:
            FileFormatError: If serialization or file operations fail
        """
        target_path = Path(file_path) if isinstance(file_path, str) else file_path

        logger.info("Writing %d models to %s", len(models), target_path)

        # Recursive prevention - exclude file temporarily
        exclusion_duration = getattr(self.config, 'default_debounce', 1.0)
        self._debounce.exclude_file_temporarily(target_path, exclusion_duration)
        logger.debug("Temporarily excluded %s from processing for %ss", target_path, exclusion_duration)

        # Create parent directories
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Auto-detect format and write
        format_handler = self._format_detector.detect_format(target_path)
        logger.debug("Detected format: %s for file: %s", format_handler.__class__.__name__, target_path)
        try:
            content = format_handler.write(models)
        except Exception as exc:
            raise FileFormatError(f"Failed to serialize models for {target_path}: {exc}") from exc

        self._atomic_write(target_path, content)
        logger.info("Successfully wrote %d models to %s", len(models), target_path)

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
                self._debounce.clear_all()
            logger.info("Watchdantic observer stopped")

    @staticmethod
    def _validate_handler_signature(func: Callable[..., Any], model_class: Type[BaseModel]) -> None:
        """Validate handler function signature matches expected pattern."""
        sig = inspect.signature(func)
        params = list(sig.parameters.values())

        if len(params) != 2:
            raise ConfigurationError(
                f"Handler '{func.__name__}' must accept exactly two parameters: "
                f"(models: List[{model_class.__name__}], file_path: Path)"
            )

        models_param, path_param = params[0], params[1]

        try:
            type_hints = typing.get_type_hints(func)
        except (NameError, AttributeError):
            # Fallback for string annotations
            return

        # Validate first parameter is List[model_class]
        models_type = type_hints.get(models_param.name)
        if models_type is not None:
            origin = get_origin(models_type)
            args = get_args(models_type)

            # Handle both typing.List and built-in list
            is_list = origin in (list, List) or (
                hasattr(models_type, "__origin__") and models_type.__origin__ in (list, List)
            )
            correct_model = len(args) == 1 and args[0] == model_class

            if not (is_list and correct_model):
                raise ConfigurationError(
                    f"Handler '{func.__name__}' first parameter must be annotated as "
                    f"List[{model_class.__name__}], got: {models_type}"
                )

        # Validate second parameter is Path
        path_type = type_hints.get(path_param.name)
        if path_type is not None and path_type is not Path:
            raise ConfigurationError(f"Handler '{func.__name__}' second parameter must be annotated as pathlib.Path")

        # Validate return type is None
        ret = type_hints.get("return")
        if ret not in (inspect._empty, type(None), None):
            raise ConfigurationError(f"Handler '{func.__name__}' must return None")

    def _atomic_write(self, target_path: Path, content: str) -> None:
        """Perform atomic write using temporary file and rename."""
        temp_fd = None
        temp_path = None
        try:
            temp_fd, temp_path_str = tempfile.mkstemp(
                dir=target_path.parent,
                prefix=f".{target_path.name}.",
                suffix=".tmp"
            )
            temp_path = Path(temp_path_str)

            with os.fdopen(temp_fd, "w", encoding="utf-8") as temp_file:
                temp_file.write(content)
                temp_file.flush()
                os.fsync(temp_file.fileno())
            temp_fd = None

            temp_path.replace(target_path)
            temp_path = None

        except Exception as exc:
            raise FileFormatError(f"Failed to write file {target_path}: {exc}") from exc
        finally:
            if temp_fd is not None:
                try:
                    os.close(temp_fd)
                except OSError:
                    pass
            if temp_path is not None and temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass