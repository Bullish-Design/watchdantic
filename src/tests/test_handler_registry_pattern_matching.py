from __future__ import annotations

from pathlib import Path
from typing import List

import pytest
from pydantic import BaseModel

from watchdantic.core.models import HandlerRegistry, HandlerInfo


# Ignore the test model (pytest is picking it up as a test case):
import warnings

warnings.filterwarnings("ignore", message="cannot collect test class 'TestModel' because it has a __init__ constructor")


class TestModel(BaseModel):
    id: str
    value: int


class TestHandlerRegistryPatternMatching:
    """Test pattern matching improvements for HandlerRegistry."""

    def test_simple_pattern_matches_filename_only(self) -> None:
        """Test that simple patterns like *.jsonl match against filename only."""
        registry = HandlerRegistry()

        def dummy_handler(models: List[TestModel], file_path: Path) -> None:
            pass

        info = HandlerInfo(handler_func=dummy_handler, model_class=TestModel, pattern="*.jsonl", debounce=1.0)
        registry.register(info)

        # Should match files with .jsonl extension regardless of path
        test_cases = [
            Path("test.jsonl"),
            Path("/absolute/path/to/test.jsonl"),
            Path("nested/dir/structure/test.jsonl"),
            Path("../relative/path/test.jsonl"),
        ]

        for test_path in test_cases:
            handlers = registry.get_handlers_for_path(test_path)
            assert len(handlers) == 1
            assert handlers[0] == info

    def test_complex_pattern_matches_full_path(self) -> None:
        """Test that complex patterns with path separators match against full path."""
        registry = HandlerRegistry()

        def dummy_handler(models: List[TestModel], file_path: Path) -> None:
            pass

        info = HandlerInfo(handler_func=dummy_handler, model_class=TestModel, pattern="logs/**/*.jsonl", debounce=1.0)
        registry.register(info)

        # Should match files in logs directory structure
        matching_paths = [
            Path("logs/app.jsonl"),
            Path("logs/subdir/app.jsonl"),
            Path("logs/deep/nested/structure/app.jsonl"),
        ]

        for test_path in matching_paths:
            handlers = registry.get_handlers_for_path(test_path)
            assert len(handlers) == 1
            assert handlers[0] == info

        # Should not match files outside logs directory
        non_matching_paths = [
            Path("app.jsonl"),
            Path("data/app.jsonl"),
            Path("other/logs/app.jsonl"),  # logs not at start
        ]

        for test_path in non_matching_paths:
            handlers = registry.get_handlers_for_path(test_path)
            assert len(handlers) == 0

    def test_mixed_patterns_work_independently(self) -> None:
        """Test that simple and complex patterns can coexist."""
        registry = HandlerRegistry()

        def handler1(models: List[TestModel], file_path: Path) -> None:
            pass

        def handler2(models: List[TestModel], file_path: Path) -> None:
            pass

        info1 = HandlerInfo(
            handler_func=handler1,
            model_class=TestModel,
            pattern="*.json",  # Simple pattern
            debounce=1.0,
        )

        info2 = HandlerInfo(
            handler_func=handler2,
            model_class=TestModel,
            pattern="config/*.json",  # Complex pattern
            debounce=1.0,
        )

        registry.register(info1)
        registry.register(info2)

        # Test file that should match both patterns
        test_path = Path("config/app.json")
        handlers = registry.get_handlers_for_path(test_path)
        assert len(handlers) == 2
        assert info1 in handlers
        assert info2 in handlers

        # Test file that should match only simple pattern
        test_path = Path("data.json")
        handlers = registry.get_handlers_for_path(test_path)
        assert len(handlers) == 1
        assert handlers[0] == info1

    def test_exclusion_patterns_use_full_path(self) -> None:
        """Test that exclusion patterns always use full path matching."""
        registry = HandlerRegistry()

        def dummy_handler(models: List[TestModel], file_path: Path) -> None:
            pass

        info = HandlerInfo(
            handler_func=dummy_handler,
            model_class=TestModel,
            pattern="*.json",
            debounce=1.0,
            exclude_patterns=["temp/*"],
        )
        registry.register(info)

        # Should match normal files
        normal_file = Path("app.json")
        handlers = registry.get_handlers_for_path(normal_file)
        assert len(handlers) == 1

        # Should exclude files in temp directory
        temp_file = Path("temp/app.json")
        handlers = registry.get_handlers_for_path(temp_file)
        assert len(handlers) == 0
