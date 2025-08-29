from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import List
from unittest.mock import patch, mock_open

import pytest
from pydantic import BaseModel

from watchdantic.core.watcher import WatchdanticCore
from watchdantic.exceptions import FileFormatError


# Ignore the test model (pytest is picking it up as a test case):
import warnings

warnings.filterwarnings("ignore", message="cannot collect test class 'TestModel' because it has a __init__ constructor")


class TestModel(BaseModel):
    """Test model for write operations."""

    id: str
    name: str
    value: int


class TestWriteOperations:
    """Test suite for write_models functionality."""

    def test_write_single_model_to_json_file(self, tmp_path: Path):
        """Test writing single model to .json file produces object."""
        watcher = WatchdanticCore()
        model = TestModel(id="1", name="test", value=42)
        target = tmp_path / "single.json"

        watcher.write_models([model], target)

        # Should be a JSON object, not array
        content = target.read_text()
        data = json.loads(content)
        assert isinstance(data, dict)
        assert data == {"id": "1", "name": "test", "value": 42}

    def test_write_multiple_models_to_json_file(self, tmp_path: Path):
        """Test writing multiple models to .json file produces array."""
        watcher = WatchdanticCore()
        models = [TestModel(id="1", name="first", value=10), TestModel(id="2", name="second", value=20)]
        target = tmp_path / "multiple.json"

        watcher.write_models(models, target)

        # Should be a JSON array
        content = target.read_text()
        data = json.loads(content)
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0] == {"id": "1", "name": "first", "value": 10}
        assert data[1] == {"id": "2", "name": "second", "value": 20}

    def test_write_empty_models_to_json_file(self, tmp_path: Path):
        """Test writing empty model list to .json file produces empty array."""
        watcher = WatchdanticCore()
        target = tmp_path / "empty.json"

        watcher.write_models([], target)

        content = target.read_text()
        data = json.loads(content)
        assert data == []

    def test_write_models_to_jsonl_file(self, tmp_path: Path):
        """Test writing models to .jsonl file produces line-delimited JSON."""
        watcher = WatchdanticCore()
        models = [TestModel(id="1", name="first", value=10), TestModel(id="2", name="second", value=20)]
        target = tmp_path / "data.jsonl"

        watcher.write_models(models, target)

        content = target.read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 2

        # Each line should be valid JSON
        assert json.loads(lines[0]) == {"id": "1", "name": "first", "value": 10}
        assert json.loads(lines[1]) == {"id": "2", "name": "second", "value": 20}

    def test_write_empty_models_to_jsonl_file(self, tmp_path: Path):
        """Test writing empty model list to .jsonl file produces just newline."""
        watcher = WatchdanticCore()
        target = tmp_path / "empty.jsonl"

        watcher.write_models([], target)

        content = target.read_text()
        assert content == "\n"

    def test_write_to_nonexistent_directory(self, tmp_path: Path):
        """Test writing to non-existent directory creates directories."""
        watcher = WatchdanticCore()
        model = TestModel(id="1", name="test", value=42)
        target = tmp_path / "nested" / "deep" / "path" / "file.json"

        # Verify directory doesn't exist
        assert not target.parent.exists()

        watcher.write_models([model], target)

        # Directory should be created and file should exist
        assert target.exists()
        assert target.parent.exists()
        data = json.loads(target.read_text())
        assert data == {"id": "1", "name": "test", "value": 42}

    def test_write_string_path(self, tmp_path: Path):
        """Test write_models accepts string paths."""
        watcher = WatchdanticCore()
        model = TestModel(id="1", name="test", value=42)
        target_path = str(tmp_path / "string_path.json")

        watcher.write_models([model], target_path)

        assert Path(target_path).exists()
        data = json.loads(Path(target_path).read_text())
        assert data == {"id": "1", "name": "test", "value": 42}

    def test_format_detection_jsonl_extension(self, tmp_path: Path):
        """Test format detection for .jsonl extension."""
        watcher = WatchdanticCore()
        model = TestModel(id="1", name="test", value=42)
        target = tmp_path / "data.jsonl"

        watcher.write_models([model], target)

        # Should use JsonLines format (line-delimited)
        content = target.read_text()
        assert content == '{"id":"1","name":"test","value":42}\n'

    def test_format_detection_jsonlines_extension(self, tmp_path: Path):
        """Test format detection for .jsonlines extension."""
        watcher = WatchdanticCore()
        model = TestModel(id="1", name="test", value=42)
        target = tmp_path / "data.jsonlines"

        watcher.write_models([model], target)

        # Should use JsonLines format
        content = target.read_text()
        assert content == '{"id":"1","name":"test","value":42}\n'

    def test_format_detection_unknown_extension_defaults_to_jsonl(self, tmp_path: Path):
        """Test unknown extensions default to JsonLines format."""
        watcher = WatchdanticCore()
        model = TestModel(id="1", name="test", value=42)
        target = tmp_path / "data.unknown"

        watcher.write_models([model], target)

        # Should default to JsonLines format
        content = target.read_text()
        assert content == '{"id":"1","name":"test","value":42}\n'

    def test_atomic_write_behavior(self, tmp_path: Path):
        """Test atomic write behavior using temporary files."""
        watcher = WatchdanticCore()
        model = TestModel(id="1", name="test", value=42)
        target = tmp_path / "atomic.json"

        # Monitor for temporary files during write
        temp_files_seen = []
        original_mkstemp = tempfile.mkstemp

        def mock_mkstemp(*args, **kwargs):
            fd, path = original_mkstemp(*args, **kwargs)
            temp_files_seen.append(Path(path))
            return fd, path

        with patch("tempfile.mkstemp", side_effect=mock_mkstemp):
            watcher.write_models([model], target)

        # Should have created temp file in same directory
        assert len(temp_files_seen) == 1
        temp_file = temp_files_seen[0]
        assert temp_file.parent == target.parent
        assert temp_file.name.startswith(f".{target.name}.")
        assert temp_file.name.endswith(".tmp")

        # Temp file should be cleaned up
        assert not temp_file.exists()

        # Target file should exist with correct content
        assert target.exists()
        data = json.loads(target.read_text())
        assert data == {"id": "1", "name": "test", "value": 42}

    def test_atomic_write_cleanup_on_failure(self, tmp_path: Path):
        """Test temporary file cleanup when write fails."""
        watcher = WatchdanticCore()
        model = TestModel(id="1", name="test", value=42)
        target = tmp_path / "fail.json"

        temp_files_created = []
        original_mkstemp = tempfile.mkstemp

        def mock_mkstemp(*args, **kwargs):
            fd, path = original_mkstemp(*args, **kwargs)
            temp_files_created.append(Path(path))
            return fd, path

        # Mock os.fsync to raise an error
        with (
            patch("tempfile.mkstemp", side_effect=mock_mkstemp),
            patch("os.fsync", side_effect=OSError("Simulated disk error")),
        ):
            with pytest.raises(FileFormatError, match="Failed to write file"):
                watcher.write_models([model], target)

        # Temporary file should be cleaned up even on failure
        assert len(temp_files_created) == 1
        temp_file = temp_files_created[0]
        assert not temp_file.exists()

        # Target file should not exist
        assert not target.exists()

    def test_serialization_error_handling(self, tmp_path: Path):
        """Test error handling when model serialization fails."""
        watcher = WatchdanticCore()
        target = tmp_path / "error.json"

        class BadModel(BaseModel):
            value: int

            def model_dump(self):
                raise ValueError("Serialization error")

        bad_model = BadModel(value=42)

        with pytest.raises(FileFormatError, match="Failed to serialize models"):
            watcher.write_models([bad_model], target)

        # File should not be created on serialization error
        assert not target.exists()

    def test_write_to_existing_file_overwrites(self, tmp_path: Path):
        """Test writing to existing file overwrites content."""
        watcher = WatchdanticCore()
        target = tmp_path / "overwrite.json"

        # Write initial content
        target.write_text('{"old": "content"}')
        assert target.exists()

        # Write new content
        model = TestModel(id="1", name="new", value=100)
        watcher.write_models([model], target)

        # Should be overwritten
        data = json.loads(target.read_text())
        assert data == {"id": "1", "name": "new", "value": 100}

    def test_permission_error_handling(self, tmp_path: Path):
        """Test handling of permission errors during write."""
        watcher = WatchdanticCore()
        model = TestModel(id="1", name="test", value=42)
        target = tmp_path / "readonly.json"

        # Create readonly parent directory (on systems that support it)
        if os.name != "nt":  # Skip on Windows where readonly dirs work differently
            readonly_dir = tmp_path / "readonly"
            readonly_dir.mkdir()
            readonly_dir.chmod(0o444)  # Read-only
            target = readonly_dir / "file.json"

            try:
                with pytest.raises(FileFormatError, match="Failed to write file"):
                    watcher.write_models([model], target)
            finally:
                # Cleanup: restore permissions so pytest can clean up
                readonly_dir.chmod(0o755)

    def test_integration_with_jsonlines_format(self, tmp_path: Path):
        """Test integration with JsonLines format handler."""
        from watchdantic.formats.jsonlines import JsonLines

        watcher = WatchdanticCore()
        models = [TestModel(id="1", name="first", value=10), TestModel(id="2", name="second", value=20)]
        target = tmp_path / "jsonlines.jsonl"

        watcher.write_models(models, target)

        # Verify format matches JsonLines expectations
        content = target.read_text()
        lines = content.strip().split("\n")

        # Should have two lines plus empty line at end
        assert len(lines) == 2
        assert json.loads(lines[0]) == {"id": "1", "name": "first", "value": 10}
        assert json.loads(lines[1]) == {"id": "2", "name": "second", "value": 20}

        # Should end with newline
        assert content.endswith("\n")

    def test_integration_with_jsonsingle_format(self, tmp_path: Path):
        """Test integration with JsonSingle format handler."""
        from watchdantic.formats.jsonsingle import JsonSingle

        watcher = WatchdanticCore()
        target = tmp_path / "jsonsingle.json"

        # Test single model -> object
        single_model = [TestModel(id="1", name="single", value=100)]
        watcher.write_models(single_model, target)

        data = json.loads(target.read_text())
        assert isinstance(data, dict)
        assert data == {"id": "1", "name": "single", "value": 100}

        # Test multiple models -> array
        multiple_models = [TestModel(id="1", name="first", value=10), TestModel(id="2", name="second", value=20)]
        watcher.write_models(multiple_models, target)

        data = json.loads(target.read_text())
        assert isinstance(data, list)
        assert len(data) == 2

    def test_logging_during_write_operations(self, tmp_path: Path, caplog):
        """Test that appropriate logging occurs during write operations."""
        import logging

        watcher = WatchdanticCore()
        model = TestModel(id="1", name="test", value=42)
        target = tmp_path / "logged.json"

        with caplog.at_level(logging.INFO):
            watcher.write_models([model], target)

        # Check for expected log messages
        log_messages = [record.message for record in caplog.records]
        assert any("Writing 1 models to" in msg for msg in log_messages)
        assert any("Successfully wrote 1 models to" in msg for msg in log_messages)

    def test_detect_format_for_path_method(self):
        """Test the _detect_format_for_path method directly."""
        from watchdantic.formats.jsonlines import JsonLines
        from watchdantic.formats.jsonsingle import JsonSingle

        watcher = WatchdanticCore()

        # Test .json extension
        json_format = watcher._detect_format_for_path(Path("test.json"))
        assert isinstance(json_format, JsonSingle)

        # Test .jsonl extension
        jsonl_format = watcher._detect_format_for_path(Path("test.jsonl"))
        assert isinstance(jsonl_format, JsonLines)

        # Test .jsonlines extension
        jsonlines_format = watcher._detect_format_for_path(Path("test.jsonlines"))
        assert isinstance(jsonlines_format, JsonLines)

        # Test unknown extension defaults to JsonLines
        unknown_format = watcher._detect_format_for_path(Path("test.unknown"))
        assert isinstance(unknown_format, JsonLines)

    def test_case_insensitive_extension_detection(self, tmp_path: Path):
        """Test that extension detection is case insensitive."""
        watcher = WatchdanticCore()
        model = TestModel(id="1", name="test", value=42)

        # Test uppercase extensions
        json_target = tmp_path / "test.JSON"
        watcher.write_models([model], json_target)
        data = json.loads(json_target.read_text())
        assert isinstance(data, dict)  # Should use JsonSingle

        jsonl_target = tmp_path / "test.JSONL"
        watcher.write_models([model], jsonl_target)
        content = jsonl_target.read_text()
        assert content == '{"id":"1","name":"test","value":42}\n'  # Should use JsonLines
