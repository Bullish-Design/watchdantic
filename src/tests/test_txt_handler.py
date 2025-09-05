from __future__ import annotations

import pytest
from pathlib import Path
from pydantic import BaseModel, ValidationError

from watchdantic.formats.txt import TxtSingle
from watchdantic.exceptions import FileFormatError


class TextDocument(BaseModel):
    content: str


class SimpleText(BaseModel):
    text: str


class ValueModel(BaseModel):
    value: str


class DataModel(BaseModel):
    data: str


class ComplexModel(BaseModel):
    title: str
    content: str
    tags: list[str] = []


class TestTxtSingle:
    def test_get_extension(self):
        handler = TxtSingle()
        assert handler.get_extension() == ".txt"

    def test_parse_with_content_field(self):
        handler = TxtSingle()
        content = "This is a test document.\n\nIt has multiple lines."

        models = handler.parse(content, TextDocument)
        assert len(models) == 1

        model = models[0]
        assert model.content == content

    def test_parse_with_text_field(self):
        handler = TxtSingle()
        content = "Simple text content"

        models = handler.parse(content, SimpleText)
        assert len(models) == 1

        model = models[0]
        assert model.text == content

    def test_parse_with_value_field(self):
        handler = TxtSingle()
        content = "Value content"

        models = handler.parse(content, ValueModel)
        assert len(models) == 1

        model = models[0]
        assert model.value == content

    def test_parse_with_data_field(self):
        handler = TxtSingle()
        content = "Data content"

        models = handler.parse(content, DataModel)
        assert len(models) == 1

        model = models[0]
        assert model.data == content

    def test_parse_empty_content_with_allowing_model(self):
        handler = TxtSingle()

        # Test with a model that should allow empty content
        models = handler.parse("", TextDocument)
        assert len(models) == 1
        assert models[0].content == ""

    def test_parse_empty_content_with_restricting_model(self):
        # Create a model that doesn't allow empty content
        class StrictModel(BaseModel):
            content: str

            @classmethod
            def model_validate(cls, value):
                if isinstance(value, dict) and value.get("content") == "":
                    raise ValueError("Content cannot be empty")
                return super().model_validate(value)

        handler = TxtSingle()
        models = handler.parse("", StrictModel)
        # Should return empty list for models that don't accept empty content
        assert models == []

    def test_parse_validation_error_bubbles(self):
        # Model that expects a specific format
        class NumberModel(BaseModel):
            content: int

        handler = TxtSingle()

        with pytest.raises(ValidationError):
            handler.parse("not a number", NumberModel)

    def test_write_with_content_field(self):
        handler = TxtSingle()
        model = TextDocument(content="This is test content\nwith multiple lines.")

        result = handler.write([model])
        assert result == "This is test content\nwith multiple lines."

    def test_write_with_text_field(self):
        handler = TxtSingle()
        model = SimpleText(text="Simple text")

        result = handler.write([model])
        assert result == "Simple text"

    def test_write_with_single_field_model(self):
        handler = TxtSingle()
        model = ValueModel(value="Single value")

        result = handler.write([model])
        assert result == "Single value"

    def test_write_with_complex_model_fallback(self):
        handler = TxtSingle()
        model = ComplexModel(title="Test", content="Test content", tags=["tag1", "tag2"])

        result = handler.write([model])
        # Should fall back to string representation of the model
        assert "Test" in result

    def test_write_empty_models(self):
        handler = TxtSingle()
        result = handler.write([])
        assert result == ""

    def test_write_multiple_models_uses_first(self):
        handler = TxtSingle()
        model1 = TextDocument(content="First document")
        model2 = TextDocument(content="Second document")

        result = handler.write([model1, model2])
        assert result == "First document"

    def test_read_models_from_file(self, tmp_path: Path):
        handler = TxtSingle()

        # Create test text file
        test_file = tmp_path / "test.txt"
        test_content = "This is file content.\n\nMultiple lines here."
        test_file.write_text(test_content)

        models = handler.read_models(test_file, TextDocument)
        assert len(models) == 1

        model = models[0]
        assert model.content == test_content

    def test_read_models_file_not_found(self, tmp_path: Path):
        handler = TxtSingle()
        missing_file = tmp_path / "missing.txt"

        with pytest.raises(FileFormatError, match="Failed to read file"):
            handler.read_models(missing_file, TextDocument)

    def test_write_with_none_values(self):
        class OptionalModel(BaseModel):
            content: str | None = None

        handler = TxtSingle()
        model = OptionalModel(content=None)

        result = handler.write([model])
        assert result == ""

    def test_model_allows_empty_content_detection(self):
        handler = TxtSingle()

        # Should detect that TextDocument allows empty content
        assert handler._model_allows_empty_content(TextDocument) is True

        # Test with a model that might not allow empty content
        class StrictModel(BaseModel):
            content: str

            @classmethod
            def model_validate(cls, value):
                if isinstance(value, dict) and not value.get("content"):
                    raise ValueError("Content required")
                return super().model_validate(value)

        # This should return False
        assert handler._model_allows_empty_content(StrictModel) is False

    def test_parse_fallback_patterns(self):
        # Test that parser can handle models with various field patterns
        class UnusualModel(BaseModel):
            weird_field: str

        handler = TxtSingle()

        # This should raise validation error since no common field names match
        with pytest.raises(ValidationError):
            handler.parse("some content", UnusualModel)

