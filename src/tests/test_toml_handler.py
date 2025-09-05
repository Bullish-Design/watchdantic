from __future__ import annotations

import pytest
from pathlib import Path
from pydantic import BaseModel, ValidationError

from watchdantic.formats.toml import TomlSingle
from watchdantic.exceptions import FileFormatError


class TestConfig(BaseModel):
    name: str
    version: str
    debug: bool = False
    ports: list[int] = []


class TestTomlSingle:
    def test_get_extension(self):
        handler = TomlSingle()
        assert handler.get_extension() == ".toml"

    def test_parse_valid_toml(self):
        handler = TomlSingle()
        content = """
        name = "test-app"
        version = "1.0.0"
        debug = true
        ports = [8000, 8001, 8002]
        """

        models = handler.parse(content, TestConfig)
        assert len(models) == 1

        model = models[0]
        assert model.name == "test-app"
        assert model.version == "1.0.0"
        assert model.debug is True
        assert model.ports == [8000, 8001, 8002]

    def test_parse_empty_content(self):
        handler = TomlSingle()
        models = handler.parse("", TestConfig)
        assert models == []

        models = handler.parse("   \n  ", TestConfig)
        assert models == []

    def test_parse_invalid_toml(self):
        handler = TomlSingle()
        invalid_content = """
        name = "test-app
        version = 1.0.0  # missing quotes
        """

        with pytest.raises(FileFormatError, match="Invalid TOML content"):
            handler.parse(invalid_content, TestConfig)

    def test_parse_validation_error_bubbles(self):
        handler = TomlSingle()
        content = """
        name = "test-app"
        version = 123  # should be string
        """

        with pytest.raises(ValidationError):
            handler.parse(content, TestConfig)

    def test_write_single_model(self):
        handler = TomlSingle()
        model = TestConfig(name="test-app", version="1.0.0", debug=True, ports=[8000, 8001])

        result = handler.write([model])

        assert 'name = "test-app"' in result
        assert 'version = "1.0.0"' in result
        assert "debug = true" in result
        # TOML can format arrays in multiple ways, check for both values
        assert "8000" in result
        assert "8001" in result
        assert "ports =" in result

    def test_write_empty_models(self):
        handler = TomlSingle()
        result = handler.write([])
        assert result == ""

    def test_write_multiple_models_uses_first(self):
        handler = TomlSingle()
        model1 = TestConfig(name="first", version="1.0")
        model2 = TestConfig(name="second", version="2.0")

        result = handler.write([model1, model2])

        # Should only contain first model
        assert 'name = "first"' in result
        assert 'name = "second"' not in result

    def test_read_models_from_file(self, tmp_path: Path):
        handler = TomlSingle()

        # Create test TOML file
        test_file = tmp_path / "test.toml"
        test_file.write_text("""
        name = "file-test"
        version = "2.0.0"
        debug = false
        ports = [3000]
        """)

        models = handler.read_models(test_file, TestConfig)
        assert len(models) == 1

        model = models[0]
        assert model.name == "file-test"
        assert model.version == "2.0.0"
        assert model.debug is False
        assert model.ports == [3000]

    def test_read_models_file_not_found(self, tmp_path: Path):
        handler = TomlSingle()
        missing_file = tmp_path / "missing.toml"

        with pytest.raises(FileFormatError, match="Failed to read file"):
            handler.read_models(missing_file, TestConfig)

    def test_write_requires_tomli_w(self, monkeypatch):
        # Mock tomli_w as None to test error handling
        import watchdantic.formats.toml as toml_module

        monkeypatch.setattr(toml_module, "tomli_w", None)

        handler = TomlSingle()
        model = TestConfig(name="test", version="1.0")

        with pytest.raises(FileFormatError, match="tomli_w package is required"):
            handler.write([model])

    def test_write_serialization_error(self):
        # Test with a model that can't be serialized to TOML
        class BadModel(BaseModel):
            data: dict = {"key": object()}  # object() can't be serialized

        handler = TomlSingle()
        bad_model = BadModel()

        with pytest.raises(FileFormatError, match="Failed to serialize model to TOML"):
            handler.write([bad_model])

