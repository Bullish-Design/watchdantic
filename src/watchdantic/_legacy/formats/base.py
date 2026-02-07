# src/watchdantic/formats/base.py
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Type, TypeVar
from pydantic import BaseModel

# Note: We only *reference* FileFormatError here in docstrings to avoid importing
# during module import in environments where exceptions may not yet be defined.
# Implementations are expected to raise watchdantic.exceptions.FileFormatError
# (or let ValidationError bubble up) as appropriate.

ModelT = TypeVar("ModelT", bound=BaseModel)


class FileFormatBase(ABC):
    """
    Abstract base class defining the contract for Watchdantic file format handlers.

    A format handler encapsulates the logic for:
      - Parsing raw file *content* into a list of validated Pydantic model instances.
      - Writing a list of Pydantic model instances back into serialized *content*.
      - Advertising the file extension it is responsible for (e.g., ".jsonl", ".json").

    Design notes
    ------------
    * **Validation**: Implementations should use the provided `model_class` to validate
      deserialized data (e.g., via Pydantic's `model_validate`, `model_validate_json`,
      or similar). Pydantic's `ValidationError` must be allowed to propagate to the
      caller to preserve precise error information.
    * **Error handling**: For *format-specific* failures (malformed syntax, I/O-free
      serialization inconsistencies, etc.), implementations should raise
      `watchdantic.exceptions.FileFormatError`. This separates validation errors (which
      are model/data issues) from format/codec errors (which are representation issues).
    * **Immutability**: Implementations should not mutate the provided models and are
      expected to return a newly serialized string in `write()`.

    Subclasses must be small, composable units with zero global state
    """

    @abstractmethod
    def parse(self, content: str, model_class: Type[BaseModel]) -> List[BaseModel]:
        """
        Parse raw file content and return a list of validated Pydantic models.

        Parameters
        ----------
        content:
            The full textual content of a file in this format.
        model_class:
            A Pydantic `BaseModel` subclass that each parsed item must validate against.
            Implementations should use `model_class` to construct/validate instances
            (e.g., `model_class.model_validate(...)` or `model_class.model_validate_json(...)`).

        Returns
        -------
        list[pydantic.BaseModel]
            A list of validated model instances. Implementations should return an empty
            list when `content` contains zero records (not `None`).

        Raises
        ------
        pydantic.ValidationError
            If data was syntactically valid for the format but failed schema validation.
        watchdantic.exceptions.FileFormatError
            If the content is malformed for the format (e.g., bad delimiters, corrupted
            encoding, invalid JSON syntax for a JSON-based format), or if a format-
            specific error prevents parsing.
        """
        raise NotImplementedError

    @abstractmethod
    def read_models(self, file_path: Path, model_type: Type[ModelT]) -> List[ModelT]:
        pass

    @abstractmethod
    def write(self, models: List[BaseModel]) -> str:
        """
        Serialize a list of Pydantic models into this format's textual representation.

        Parameters
        ----------
        models:
            A list of Pydantic model instances to serialize. Implementations may
            impose additional constraints (e.g., non-empty lists) but should document
            them clearly.

        Returns
        -------
        str
            The serialized textual content representing the provided models.

        Raises
        ------
        watchdantic.exceptions.FileFormatError
            If a format-specific error occurs during serialization, such as unsupported
            field types, invalid characters for the target format, or other codec issues.
        """
        raise NotImplementedError

    @abstractmethod
    def get_extension(self) -> str:
        """
        Return the canonical file extension (including the leading dot) handled by this format.

        Examples
        --------
        - ".jsonl" for JSON Lines
        - ".json" for single JSON documents

        Returns
        -------
        str
            The file extension including the leading dot.

        Notes
        -----
        Implementations should return a lowercase extension and must not include wildcards.

        Raises
        ------
        None
        """
        raise NotImplementedError
