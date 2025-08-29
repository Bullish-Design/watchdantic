from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, TYPE_CHECKING

from pydantic import BaseModel, Field, ValidationError

from ..exceptions import FileFormatError

if TYPE_CHECKING:
    from .config import WatchdanticConfig


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

    config: WatchdanticConfig
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
        """Attach a handler and level, ensuring no duplicates."""
        # This logger is specific, so we can control its handlers directly.
        if self.logger.hasHandlers():
            self.logger.handlers.clear()

        desired_level = self._level_to_int(getattr(self.config, "log_level", "INFO"))
        self.logger.setLevel(desired_level)

        target_is_file = getattr(self.config, "log_file", None) is not None
        target_path = Path(self.config.log_file) if target_is_file else None

        if target_is_file:
            handler: logging.Handler = logging.FileHandler(target_path, encoding="utf-8", mode="a") 
        else:
            handler = logging.StreamHandler(stream=sys.stdout)
        handler.setLevel(desired_level)
        handler.setFormatter(logging.Formatter(fmt="%(message)s"))
        self.logger.addHandler(handler)

        # Debug note that the logger was configured
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
