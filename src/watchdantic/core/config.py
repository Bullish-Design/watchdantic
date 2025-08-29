from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator, ConfigDict


class WatchdanticConfig(BaseModel):
    """
    Global configuration for Watchdantic.

    This configuration model includes settings for debouncing, error handling,
    file processing limits, recursive prevention, and structured logging control.
    """

    # --- Core behavior ---
    default_debounce: float = Field(default=1.0, ge=0.0, description="Default debounce time in seconds")
    continue_on_error: bool = Field(default=False, description="Continue processing on validation errors")
    recursive: bool = Field(default=True, description="Watch subdirectories recursively")
    max_file_size_mb: int = Field(default=100, gt=0, description="Maximum file size in MB")

    # --- Logging controls ---
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
            logger.debug(
                "WatchdanticConfig initialized",
                extra={
                    "watchdantic": {
                        "default_debounce": self.default_debounce,
                        "continue_on_error": self.continue_on_error,
                        "recursive": self.recursive,
                        "max_file_size_mb": self.max_file_size_mb,
                        "enable_logging": self.enable_logging,
                        "log_level": self.log_level,
                        "log_file": str(self.log_file) if self.log_file else None,
                    }
                },
            )
        except Exception:
            # Never allow logging to disrupt normal operation
            logger.debug("WatchdanticConfig initialized (logging of extras failed safely)")
