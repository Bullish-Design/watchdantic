from __future__ import annotations

from watchdantic.core.watcher import Watchdantic
from watchdantic.core.config import WatchdanticConfig
from watchdantic.formats import JsonLines, JsonSingle, FormatDetector

__all__ = ["Watchdantic", "WatchdanticConfig", "JsonLines", "JsonSingle", "FormatDetector"]

__version__ = "0.2.1"
