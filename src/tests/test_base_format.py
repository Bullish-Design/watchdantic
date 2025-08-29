# src/tests/test_base_format.py
from __future__ import annotations

from typing import List, Type, get_type_hints

import json
import pytest
from pydantic import BaseModel, ValidationError

from watchdantic.formats.base import FileFormatBase


class LogEntry(BaseModel):
    timestamp: str
    level: str
    message: str


class TestFormat(FileFormatBase):
    """
    A minimal concrete implementation used for testing the abstract interface.

    Representation:
      - Each line is a JSON object representing a single model.
      - Empty content -> []
    """

    def parse(self, content: str, model_class: Type[BaseModel]) -> List[BaseModel]:
        lines = [ln for ln in content.splitlines() if ln.strip()]
        models: List[BaseModel] = []
        for ln in lines:
            try:
                # Parse JSON line to python dict (format responsibility),
                # then validate with model_class (schema responsibility).
                data = json.loads(ln)
            except json.JSONDecodeError as exc:  # format-specific error
                # In real impls, this should be watchdantic.exceptions.FileFormatError.
                # For test isolation, raise a plain ValueError to keep this file
                # independent from step ordering if exceptions aren't present yet.
                raise ValueError(f"Malformed TestFormat line: {exc}") from exc
            models.append(model_class.model_validate(data))
        return models

    def write(self, models: List[BaseModel]) -> str:
        try:
            return "\n".join(m.model_dump_json() for m in models)
        except TypeError as exc:
            # In a real impl, convert to FileFormatError. Here: surface as ValueError.
            raise ValueError(f"Unable to serialize models: {exc}") from exc

    def get_extension(self) -> str:
        return ".test"


def test_cannot_instantiate_abstract_base() -> None:
    class Incomplete(FileFormatBase):
        def parse(self, content: str, model_class: Type[BaseModel]) -> List[BaseModel]:
            return []

        # Missing write()
        def get_extension(self) -> str:
            return ".x"

    with pytest.raises(TypeError):
        _ = FileFormatBase()  # type: ignore[abstract]

    with pytest.raises(TypeError):
        _ = Incomplete()  # type: ignore[abstract]


def test_concrete_roundtrip() -> None:
    fmt = TestFormat()
    models = [
        LogEntry(timestamp="2025-08-28T12:00:00Z", level="INFO", message="Started"),
        LogEntry(timestamp="2025-08-28T12:05:00Z", level="ERROR", message="Boom"),
    ]
    content = fmt.write(models)
    parsed = fmt.parse(content, LogEntry)
    assert parsed == models
    assert fmt.get_extension() == ".test"


def test_parse_empty_content_returns_empty_list() -> None:
    fmt = TestFormat()
    out = fmt.parse("", LogEntry)
    assert out == []


def test_parse_validation_error_bubbles() -> None:
    fmt = TestFormat()
    # Missing 'message' key -> should raise ValidationError from Pydantic
    bad_line = json.dumps({"timestamp": "t", "level": "INFO"})
    with pytest.raises(ValidationError):
        fmt.parse(bad_line, LogEntry)


def test_parse_format_error() -> None:
    fmt = TestFormat()
    # Malformed JSON should be treated as a *format* error by the concrete impl.
    with pytest.raises(ValueError):
        fmt.parse("{not-json}", LogEntry)


def test_write_type_error_surfaces() -> None:
    fmt = TestFormat()

    # Create a bogus object that isn't a Pydantic model to force failure.
    class NotModel:
        def model_dump_json(self) -> str:  # wrong signature usage
            raise TypeError("nope")

    with pytest.raises(ValueError):
        fmt.write([NotModel()])  # type: ignore[arg-type]


def test_type_hints_preserved_on_abstract_methods() -> None:
    # Ensure the interface has the expected type annotations, so downstream
    # implementors get proper editor/type-checker ergonomics.
    hints_parse = get_type_hints(FileFormatBase.parse)
    assert hints_parse["content"] is str
    # Type[BaseModel] annotation preserved
    assert "model_class" in hints_parse

    hints_write = get_type_hints(FileFormatBase.write)
    assert hints_write["models"] is List[BaseModel] or str(hints_write["models"]).endswith(
        "List[pydantic.main.BaseModel]"
    )

    hints_ext = get_type_hints(FileFormatBase.get_extension)
    assert hints_ext.get("return") is str
