from __future__ import annotations

from typing import Any, List, Sequence, Type
import json
import logging
from pathlib import Path

from pydantic import BaseModel

from watchdantic.exceptions import FileFormatError
from .base import FileFormatBase

logger = logging.getLogger("watchdantic.formats.jsonsingle")


class JsonSingle(FileFormatBase):
    """Handler for `.json` files containing a single object or an array of objects.
    Parsing:
      - If file contains a JSON object, it is treated as a single model and returned as a 1-item list.
      - If file contains a JSON array, each item is validated into a model and returned as a list.
      - Empty arrays are supported and return an empty list.
      - Invalid JSON raises :class:`FileFormatError`.
      - Pydantic validation errors are not wrapped and will propagate.
    Writing:
      - All model lists are written as a JSON array (e.g., `[]`, `[{...}]`, `[{...}, {...}]`).

    All output uses compact JSON for consistency.
    """

    def get_extension(self) -> str:
        return ".json"

    def read_models(self, file_path: Path, model_type: Type[BaseModel]) -> List[BaseModel]:
        """Read models from a JSON file.
        Parameters
        ----------
        file_path:
            The path to the JSON file.
        model_type:
            The Pydantic model class used to validate the JSON content.
        Returns
        -------
        list[BaseModel]
            A list of successfully parsed and validated models.
        Raises
        ------
        FileFormatError
            If file reading fails or content is not valid JSON
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except IOError as exc:
            raise FileFormatError(f"Failed to read file {file_path}: {exc}") from exc

        return self.parse(content, model_type)

    def parse(self, content: str, model_class: Type[BaseModel]) -> List[BaseModel]:
        """Parse JSON content into a list of validated model instances.
        Args:
            content: Raw JSON file content as string
            model_class: Pydantic model class for validation

        Returns:
            List of validated model instances

        Raises:
            FileFormatError: If content is not valid JSON or has wrong structure
        """
        if not content.strip():
            logger.debug("Empty content, returning empty list")
            return []

        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise FileFormatError(f"Invalid JSON content: {e.msg} at line {e.lineno} col {e.colno}") from e

        if isinstance(data, list):
            # Allow empty list; validate each dict-like entry.
            items: Sequence[Any] = data
        elif isinstance(data, dict):
            items = [data]
        else:
            raise FileFormatError(f"Top-level JSON must be an object or array; got {type(data).__name__}")

        models: List[BaseModel] = []
        for idx, item in enumerate(items):
            # Let Pydantic raise ValidationError if invalid.
            logger.debug(f"Validating item {idx} with {model_class.__name__}")
            model = model_class.model_validate(item)
            models.append(model)

        logger.info(f"Parsed {len(models)} models from JSON content")
        return models

    def write(self, models: List[BaseModel]) -> str:
        """Serialize models to a JSON array string.

        Args:
            models: List of Pydantic models to serialize

        Returns:
            JSON string representation (always as an array).

        Raises:
            FileFormatError: If serialization fails
        """
        logger.debug(f"Writing {len(models)} models to JSON array")

        try:
            # Always serialize as an array for consistency.
            dumped_models = [m.model_dump(mode="json") for m in models]
            payload = json.dumps(dumped_models, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError) as e:
            # JSON serialization issue (e.g., non-serializable value)
            raise FileFormatError(f"Failed to serialize models to JSON: {e}") from e

        logger.info(f"Successfully serialized {len(models)} models to JSON")
        return payload
