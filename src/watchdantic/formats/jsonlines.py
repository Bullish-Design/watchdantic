from __future__ import annotations

"""JsonLines (.jsonl) file format implementation.

This module provides the :class:`JsonLines` class, a concrete implementation of
:class:`watchdantic.formats.base.FileFormatBase` for reading and writing files
containing one JSON object per line.

Design notes
------------
- Parsing is resilient: empty/whitespace lines are skipped; invalid JSON lines
  are logged at WARNING level and skipped; Pydantic ``ValidationError`` raised
  while constructing the target ``BaseModel`` **bubble up** to the caller.
- Writing emits one compact JSON object per line and always appends a trailing
  newline at the end of the string, even for an empty sequence of models.
- Any JSON serialization issues during writing are wrapped in
  :class:`watchdantic.exceptions.FileFormatError`.
"""

from typing import Iterable, List, Sequence, Type, TypeVar
import json
import logging
from pathlib import Path

from pydantic import BaseModel

from watchdantic.exceptions import FileFormatError
from watchdantic.formats.base import FileFormatBase


logger = logging.getLogger("watchdantic.formats.jsonlines")

ModelT = TypeVar("ModelT", bound=BaseModel)


class JsonLines(FileFormatBase):
    """Handler for the JSON Lines (``.jsonl``) format.

    The handler converts text where each non-empty line is a JSON object into a
    list of validated Pydantic models, and vice versa.
    """

    def get_extension(self) -> str:
        """Return the canonical file extension for this format.

        Returns
        -------
        str
            The lowercase extension, including the leading dot.
        """
        return ".jsonl"

    def parse(self, content: str, model_type: Type[ModelT]) -> List[ModelT]:
        """Parse JSONL ``content`` into a list of ``model_type`` instances.

        Parameters
        ----------
        content:
            The raw text content of a ``.jsonl`` file.
        model_type:
            The Pydantic model class used to validate each JSON object.

        Returns
        -------
        list[ModelT]
            A list of successfully parsed and validated models. Lines with
            invalid JSON are skipped. Validation errors are not caught.
        """
        models: List[ModelT] = []
        if not content:
            return models

        for idx, raw_line in enumerate(content.splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                # Skip empty/whitespace-only lines
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                logger.warning("Skipping invalid JSON line %d: %s", idx, exc.msg)
                continue

            # Let Pydantic ValidationError bubble up to the caller as specified
            model = model_type(**data)
            models.append(model)

        return models

    def write(self, models: Sequence[BaseModel]) -> str:
        """Serialize a sequence of models into JSONL text.

        Parameters
        ----------
        models:
            The sequence of Pydantic ``BaseModel`` instances to serialize.

        Returns
        -------
        str
            The serialized JSONL string with a trailing newline.

        Raises
        ------
        FileFormatError
            If an object cannot be serialized to JSON.
        """
        lines: List[str] = []
        for idx, model in enumerate(models, start=1):
            try:
                payload = model.model_dump()
                line = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
            except (TypeError, ValueError) as exc:
                raise FileFormatError(f"Failed to serialize model at index {idx}: {exc}") from exc
            lines.append(line)

        # Always end with a single trailing newline, even for empty sequences
        return "\n".join(lines) + "\n"

    def read_models(self, file_path: Path, model_type: Type[ModelT]) -> List[ModelT]:
        """Read models from a JSONL file.

        Parameters
        ----------
        file_path:
            The path to the JSONL file.
        model_type:
            The Pydantic model class used to validate each JSON object.

        Returns
        -------
        list[ModelT]
            A list of successfully parsed and validated models.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except IOError as exc:
            raise FileFormatError(f"Failed to read file {file_path}: {exc}") from exc

        return self.parse(content, model_type)
