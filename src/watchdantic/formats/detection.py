from __future__ import annotations

from pathlib import Path
from typing import Type, Dict

from .base import FileFormatBase
from .jsonlines import JsonLines
from .jsonsingle import JsonSingle
from .toml import TomlSingle
from .markdown import MarkdownWithFrontmatter
from .txt import TxtSingle


class FormatDetector:
    """Centralized format detection based on file extensions."""

    def __init__(self):
        self._formats: Dict[str, Type[FileFormatBase]] = {
            ".jsonl": JsonLines,
            ".jsonlines": JsonLines,
            ".json": JsonSingle,
            ".toml": TomlSingle,
            ".md": MarkdownWithFrontmatter,
            ".markdown": MarkdownWithFrontmatter,
            ".txt": TxtSingle,
        }
        self._default = JsonLines

    def detect_format(self, file_path: Path) -> FileFormatBase:
        """Detect and return appropriate format handler for file."""
        suffix = file_path.suffix.lower()
        format_class = self._formats.get(suffix, self._default)
        return format_class()

    def infer_from_pattern(self, pattern: str) -> FileFormatBase | None:
        """Infer format from glob pattern if possible."""
        pattern_lower = pattern.lower()

        if pattern_lower.endswith(".jsonl") or pattern_lower.endswith(".jsonlines"):
            return JsonLines()
        elif pattern_lower.endswith(".json"):
            return JsonSingle()
        elif pattern_lower.endswith(".toml"):
            return TomlSingle()
        elif pattern_lower.endswith(".md") or pattern_lower.endswith(".markdown"):
            return MarkdownWithFrontmatter()
        elif pattern_lower.endswith(".txt"):
            return TxtSingle()

        return None

    def register_format(self, extension: str, format_class: Type[FileFormatBase]) -> None:
        """Register a custom format for an extension."""
        if not extension.startswith("."):
            extension = "." + extension
        self._formats[extension.lower()] = format_class
