from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import List
from unittest.mock import Mock, patch

import pytest
from pydantic import BaseModel

from watchdantic.core.models import WatchdanticConfig, HandlerRegistry, DebounceManager
from watchdantic.core.watcher import WatchdanticCore, FileEventProcessor
from watchdantic.exceptions import ConfigurationError


# Ignore the test model (pytest is picking it up as a test case):
import warnings

warnings.filterwarnings("ignore", message="cannot collect test class 'TestModel' because it has a __init__ constructor")


class TestModel(BaseModel):
    id: str
    value: int
    processed: bool = False


class ProcessedModel(BaseModel):
    id: str
    value: int
    processed: bool = True
    transform_count: int = 1


class TestRecursivePrevention:
    """Test suite for recursive prevention functionality."""

    def test_write_models_excludes_file_temporarily(self, tmp_path: Path) -> None:
        """Test that write_models excludes the target file temporarily."""
        config = WatchdanticConfig(default_debounce=0.5)
        core = WatchdanticCore(config=config)

        test_file = tmp_path / "test.jsonl"
        models = [TestModel(id="1", value=10)]

        # File should not be excluded initially
        assert not core.debounce_manager.is_file_excluded(test_file)

        # Write models - this should exclude the file
        core.write_models(models, test_file)

        # File should now be excluded
        assert core.debounce_manager.is_file_excluded(test_file)

        # Wait for exclusion to expire
        time.sleep(0.6)  # Slightly longer than default_debounce

        # File should no longer be excluded
        assert not core.debounce_manager.is_file_excluded(test_file)

    def test_handler_writing_to_watched_file_doesnt_retrigger(self, tmp_path: Path) -> None:
        """Test that handlers writing to their own watched files don't retrigger."""
        config = WatchdanticConfig(default_debounce=0.2)
        registry = HandlerRegistry()
        debounce_manager = DebounceManager()
        processor = FileEventProcessor(registry=registry, config=config, debounce_manager=debounce_manager)
        core = WatchdanticCore(config=config, registry=registry, debounce_manager=debounce_manager)

        test_file = tmp_path / "transform.jsonl"
        execution_count = 0

        @core.triggers_on(TestModel, "*.jsonl")
        def transform_handler(models: List[TestModel], file_path: Path) -> None:
            nonlocal execution_count
            execution_count += 1

            # Transform and write back - this should NOT retrigger
            processed = [ProcessedModel(id=m.id, value=m.value * 2) for m in models]
            core.write_models(processed, file_path)

        # Create initial file content
        initial_models = [TestModel(id="1", value=5)]
        test_file.write_text('{"id": "1", "value": 5, "processed": false}\n')

        # Process the file event
        processor.process_file_event(test_file)

        # Handler should have executed once
        assert execution_count == 1

        # Verify file was written
        assert test_file.exists()
        content = test_file.read_text()
        assert '"processed":true' in content or '"processed": true' in content
        assert '"value":10' in content or '"value": 10' in content

        # Wait briefly but less than exclusion period
        time.sleep(0.1)

        # Process file again - should still be excluded
        processor.process_file_event(test_file)

        # Handler should still have executed only once (exclusion prevents retrigger)
        assert execution_count == 1

    def test_exclusion_expires_after_debounce_period(self, tmp_path: Path) -> None:
        """Test that file exclusion expires after the debounce period."""
        config = WatchdanticConfig(default_debounce=0.1)  # Short debounce for testing
        core = WatchdanticCore(config=config)
        processor = FileEventProcessor(registry=core.registry, config=config, debounce_manager=core.debounce_manager)

        test_file = tmp_path / "expire_test.jsonl"
        execution_count = 0

        @core.triggers_on(TestModel, "*.jsonl")
        def counting_handler(models: List[TestModel], file_path: Path) -> None:
            nonlocal execution_count
            execution_count += 1

        # Write initial content
        test_file.write_text('{"id": "1", "value": 5, "processed": false}\n')

        # Write models to exclude file
        models = [TestModel(id="1", value=5)]
        core.write_models(models, test_file)

        # File should be excluded
        assert core.debounce_manager.is_file_excluded(test_file)

        # Try to process - should be skipped
        processor.process_file_event(test_file)
        assert execution_count == 0

        # Wait for exclusion to expire
        time.sleep(0.15)  # Longer than debounce period

        # File should no longer be excluded
        assert not core.debounce_manager.is_file_excluded(test_file)

        # Process should now work
        processor.process_file_event(test_file)
        assert execution_count == 1

    def test_multiple_handlers_writing_different_files(self, tmp_path: Path) -> None:
        """Test that multiple handlers can write to different files independently."""
        config = WatchdanticConfig(default_debounce=0.2)
        core = WatchdanticCore(config=config)
        processor = FileEventProcessor(registry=core.registry, config=config, debounce_manager=core.debounce_manager)

        input_file = tmp_path / "input.jsonl"
        output_file1 = tmp_path / "output1.jsonl"
        output_file2 = tmp_path / "output2.jsonl"

        handler1_executions = 0
        handler2_executions = 0

        @core.triggers_on(TestModel, "input.jsonl")
        def handler1(models: List[TestModel], file_path: Path) -> None:
            nonlocal handler1_executions
            handler1_executions += 1
            processed = [ProcessedModel(id=m.id, value=m.value + 100) for m in models]
            core.write_models(processed, output_file1)

        @core.triggers_on(TestModel, "input.jsonl")
        def handler2(models: List[TestModel], file_path: Path) -> None:
            nonlocal handler2_executions
            handler2_executions += 1
            processed = [ProcessedModel(id=m.id, value=m.value + 200) for m in models]
            core.write_models(processed, output_file2)

        # Create input file
        input_file.write_text('{"id": "1", "value": 10, "processed": false}\n')

        # Process input file - should trigger both handlers
        processor.process_file_event(input_file)

        assert handler1_executions == 1
        assert handler2_executions == 1

        # Both output files should exist
        assert output_file1.exists()
        assert output_file2.exists()

        # Output files should be excluded from processing
        assert core.debounce_manager.is_file_excluded(output_file1)
        assert core.debounce_manager.is_file_excluded(output_file2)

        # Input file should not be excluded
        assert not core.debounce_manager.is_file_excluded(input_file)

    def test_exclusion_doesnt_affect_other_files(self, tmp_path: Path) -> None:
        """Test that excluding one file doesn't affect processing of other files."""
        config = WatchdanticConfig(default_debounce=0.2)
        core = WatchdanticCore(config=config)
        processor = FileEventProcessor(registry=core.registry, config=config, debounce_manager=core.debounce_manager)

        file1 = tmp_path / "file1.jsonl"
        file2 = tmp_path / "file2.jsonl"

        handler_calls = []

        @core.triggers_on(TestModel, "*.jsonl")
        def tracking_handler(models: List[TestModel], file_path: Path) -> None:
            handler_calls.append(str(file_path.name))

        # Create both files
        file1.write_text('{"id": "1", "value": 10, "processed": false}\n')
        file2.write_text('{"id": "2", "value": 20, "processed": false}\n')

        # Write models to file1 (excludes file1)
        models = [TestModel(id="1", value=10)]
        core.write_models(models, file1)

        # file1 should be excluded, file2 should not
        assert core.debounce_manager.is_file_excluded(file1)
        assert not core.debounce_manager.is_file_excluded(file2)

        # Process both files
        processor.process_file_event(file1)  # Should be skipped
        processor.process_file_event(file2)  # Should execute

        # Only file2 handler should have executed
        assert handler_calls == ["file2.jsonl"]

    def test_manual_triggers_work_during_exclusion(self, tmp_path: Path) -> None:
        """Test that manual triggers still work even when files are excluded."""
        config = WatchdanticConfig(default_debounce=0.2)
        core = WatchdanticCore(config=config)
        processor = FileEventProcessor(registry=core.registry, config=config, debounce_manager=core.debounce_manager)

        test_file = tmp_path / "manual_test.jsonl"
        execution_count = 0

        @core.triggers_on(TestModel, "*.jsonl")
        def manual_handler(models: List[TestModel], file_path: Path) -> None:
            nonlocal execution_count
            execution_count += 1

        # Create test file
        test_file.write_text('{"id": "1", "value": 5, "processed": false}\n')

        # Exclude the file manually
        core.debounce_manager.exclude_file_temporarily(test_file, 0.5)
        assert core.debounce_manager.is_file_excluded(test_file)

        # Normal file event processing should be blocked
        processor.process_file_event(test_file)
        assert execution_count == 0

        # But we can still manually call the handler
        models = [TestModel(id="1", value=5)]
        handlers = core.registry.get_handlers_for_path(test_file)
        assert len(handlers) == 1

        handler_info = handlers[0]
        handler_info.handler_func(models, test_file)
        assert execution_count == 1

    def test_concurrent_write_exclusions(self, tmp_path: Path) -> None:
        """Test that concurrent writes to different files work correctly with exclusions."""
        config = WatchdanticConfig(default_debounce=0.1)
        core = WatchdanticCore(config=config)

        files = [tmp_path / f"concurrent_{i}.jsonl" for i in range(5)]
        models = [TestModel(id=str(i), value=i) for i in range(5)]

        # Function to write models concurrently
        def write_file(file_path: Path, model: TestModel) -> None:
            core.write_models([model], file_path)

        # Start concurrent writes
        threads = []
        for file_path, model in zip(files, models):
            thread = threading.Thread(target=write_file, args=(file_path, model))
            threads.append(thread)
            thread.start()

        # Wait for all writes to complete
        for thread in threads:
            thread.join()

        # All files should exist
        for file_path in files:
            assert file_path.exists()

        # All files should be excluded initially
        for file_path in files:
            assert core.debounce_manager.is_file_excluded(file_path)

        # Wait for exclusions to expire
        time.sleep(0.15)

        # No files should be excluded now
        for file_path in files:
            assert not core.debounce_manager.is_file_excluded(file_path)

    def test_write_models_with_custom_debounce_config(self, tmp_path: Path) -> None:
        """Test that write_models respects custom debounce configuration."""
        custom_debounce = 0.3
        config = WatchdanticConfig(default_debounce=custom_debounce)
        core = WatchdanticCore(config=config)

        test_file = tmp_path / "custom_debounce.jsonl"
        models = [TestModel(id="1", value=42)]

        # Write models
        core.write_models(models, test_file)

        # File should be excluded
        assert core.debounce_manager.is_file_excluded(test_file)

        # Should still be excluded after shorter time
        time.sleep(0.1)
        assert core.debounce_manager.is_file_excluded(test_file)

        # Should still be excluded after default time but less than custom
        time.sleep(0.15)  # Total: 0.25s < 0.3s
        assert core.debounce_manager.is_file_excluded(test_file)

        # Should be unexcluded after custom debounce time
        time.sleep(0.1)  # Total: 0.35s > 0.3s
        assert not core.debounce_manager.is_file_excluded(test_file)

    def test_write_models_handles_missing_default_debounce(self, tmp_path: Path) -> None:
        """Test that write_models handles missing default_debounce gracefully."""
        # Create config without default_debounce (should use fallback)
        config = WatchdanticConfig()
        # Remove default_debounce if it exists by creating a new config
        config_dict = config.model_dump()
        if "default_debounce" in config_dict:
            del config_dict["default_debounce"]

        # Create core with config that might not have default_debounce
        core = WatchdanticCore(config=config)

        test_file = tmp_path / "fallback_test.jsonl"
        models = [TestModel(id="1", value=1)]

        # This should not raise an error and should use fallback debounce (1.0)
        core.write_models(models, test_file)

        # File should be excluded
        assert core.debounce_manager.is_file_excluded(test_file)

        # Should be unexcluded after fallback time (test with a reasonable timeout)
        time.sleep(1.1)  # Slightly more than 1.0 second fallback
        assert not core.debounce_manager.is_file_excluded(test_file)
