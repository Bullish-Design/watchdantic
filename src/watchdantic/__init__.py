from __future__ import annotations

from watchdantic.core.watcher import Watchdantic
from watchdantic.core.config import WatchdanticConfig
from watchdantic.core.pipeline import PipelineBuilder
from watchdantic.core.actions import PipelineAction, TriggerConfig
from watchdantic.formats import (
    JsonLines, JsonSingle, TomlSingle, MarkdownWithFrontmatter, TxtSingle, FormatDetector
)

__all__ = [
    "Watchdantic", 
    "WatchdanticConfig",
    "PipelineBuilder",
    "PipelineAction", 
    "TriggerConfig",
    "JsonLines", 
    "JsonSingle", 
    "TomlSingle",
    "MarkdownWithFrontmatter",
    "TxtSingle",
    "FormatDetector"
]

__version__ = "0.3.0"
