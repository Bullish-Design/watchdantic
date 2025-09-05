from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Type, TypeVar

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # fallback for Python < 3.11

try:
    import tomli_w
except ImportError:
    tomli_w = None

from pydantic import BaseModel

from watchdantic.exceptions import FileFormatError
from .base import FileFormatBase

logger = logging.getLogger("watchdantic.formats.toml")
ModelT = TypeVar("ModelT", bound=BaseModel)


class TomlSingle(FileFormatBase):
    """Handler for `.toml` files containing a single TOML document.
    
    Parsing:
      - File must contain a valid TOML document
      - The entire TOML document is treated as a single model instance
      - Invalid TOML raises FileFormatError
      - Pydantic validation errors are not wrapped and will propagate
      
    Writing:
      - Model is serialized to TOML format
      - Requires tomli_w package for writing
      - Only single models supported (first item if list provided)
    """

    def get_extension(self) -> str:
        """Return the canonical file extension for TOML files."""
        return ".toml"

    def read_models(self, file_path: Path, model_type: Type[ModelT]) -> List[ModelT]:
        """Read model from a TOML file.
        
        Parameters
        ----------
        file_path:
            The path to the TOML file.
        model_type:
            The Pydantic model class used to validate the TOML content.
            
        Returns
        -------
        list[ModelT]
            A list containing the single validated model instance.
            
        Raises
        ------
        FileFormatError
            If file reading fails or content is not valid TOML
        """
        try:
            with open(file_path, "rb") as f:
                content_bytes = f.read()
        except IOError as exc:
            raise FileFormatError(f"Failed to read file {file_path}: {exc}") from exc
            
        return self.parse(content_bytes.decode("utf-8"), model_type)

    def parse(self, content: str, model_class: Type[ModelT]) -> List[ModelT]:
        """Parse TOML content into a single validated model instance.
        
        Args:
            content: Raw TOML file content as string
            model_class: Pydantic model class for validation
            
        Returns:
            List containing single validated model instance
            
        Raises:
            FileFormatError: If content is not valid TOML
        """
        if not content.strip():
            logger.debug("Empty TOML content, returning empty list")
            return []

        try:
            data = tomllib.loads(content)
        except tomllib.TOMLDecodeError as e:
            raise FileFormatError(f"Invalid TOML content: {e}") from e

        # Let Pydantic raise ValidationError if invalid
        logger.debug(f"Validating TOML data with {model_class.__name__}")
        model = model_class.model_validate(data)
        
        logger.info("Parsed 1 model from TOML content")
        return [model]

    def write(self, models: List[BaseModel]) -> str:
        """Serialize model to TOML string.
        
        Args:
            models: List of Pydantic models (only first model used)
            
        Returns:
            TOML string representation
            
        Raises:
            FileFormatError: If tomli_w not available or serialization fails
        """
        if not models:
            logger.debug("No models provided, returning empty TOML")
            return ""
            
        if tomli_w is None:
            raise FileFormatError(
                "tomli_w package is required for writing TOML files. "
                "Install with: pip install tomli_w"
            )

        model = models[0]  # Only use first model for TOML
        if len(models) > 1:
            logger.warning("Multiple models provided to TOML writer, only using first model")

        logger.debug(f"Writing 1 model to TOML")

        try:
            data = model.model_dump(mode="json")
            result = tomli_w.dumps(data)
        except (TypeError, ValueError) as e:
            raise FileFormatError(f"Failed to serialize model to TOML: {e}") from e

        logger.info("Successfully serialized 1 model to TOML")
        return result