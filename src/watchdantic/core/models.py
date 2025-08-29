from __future__ import annotations

# Re-export all classes for backward compatibility
from .config import WatchdanticConfig
from .handlers import HandlerInfo, HandlerRegistry
from .debouncing import DebounceManager
from .logging import WatchdanticLogger

__all__ = [
    "WatchdanticConfig",
    "HandlerInfo",
    "HandlerRegistry",
    "DebounceManager",
    "WatchdanticLogger"
]
