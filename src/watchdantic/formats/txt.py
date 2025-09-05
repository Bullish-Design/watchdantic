from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Type, TypeVar

from pydantic import BaseModel

from watchdantic.exceptions import FileFormatError
from .base import FileFormatBase

logger = logging.getLogger("watchdantic.formats.txt")
ModelT = TypeVar("ModelT", bound=BaseModel)


class TxtSingle(FileFormatBase):
    """Handler for `.txt` files containing plain text content.
    
    Parsing:
      - Entire file content is treated as a single text field
      - Content is passed to model validation (typically as 'content' field)
      - Empty files result in empty list
      - Pydantic validation errors are not wrapped and will propagate
      
    Writing:
      - Model is serialized to plain text
      - Uses 'content' field if present, otherwise uses string representation
      - Only single models supported (first item if list provided)
    """

    def get_extension(self) -> str:
        """Return the canonical file extension for text files."""
        return ".txt"

    def read_models(self, file_path: Path, model_type: Type[ModelT]) -> List[ModelT]:
        """Read model from a text file.
        
        Parameters
        ----------
        file_path:
            The path to the text file.
        model_type:
            The Pydantic model class used to validate the text content.
            
        Returns
        -------
        list[ModelT]
            A list containing the single validated model instance.
            
        Raises
        ------
        FileFormatError
            If file reading fails
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except IOError as exc:
            raise FileFormatError(f"Failed to read file {file_path}: {exc}") from exc
            
        return self.parse(content, model_type)

    def parse(self, content: str, model_class: Type[ModelT]) -> List[ModelT]:
        """Parse text content into a single validated model instance.
        
        Args:
            content: Raw text file content as string
            model_class: Pydantic model class for validation
            
        Returns:
            List containing single validated model instance
            
        Raises:
            FileFormatError: If model construction fails unexpectedly
        """
        if not content and not self._model_allows_empty_content(model_class):
            logger.debug("Empty text content, returning empty list")
            return []

        # Try to construct model with content
        try:
            # Check if model has a 'content' field
            model_fields = model_class.model_fields if hasattr(model_class, 'model_fields') else {}
            
            if 'content' in model_fields:
                # Model expects a content field
                model_data = {'content': content}
            else:
                # Try to pass content directly (for simple string-based models)
                # This handles cases where the model might accept content in different ways
                model_data = content
                
            # Let Pydantic raise ValidationError if invalid
            logger.debug(f"Validating text content with {model_class.__name__}")
            model = model_class.model_validate(model_data)
            
        except Exception as e:
            # If direct content fails, try wrapping in dict
            if isinstance(model_data, str):
                try:
                    # Last resort: try common field names
                    for field_name in ['text', 'value', 'data']:
                        if field_name in model_fields:
                            model = model_class.model_validate({field_name: content})
                            break
                    else:
                        # Re-raise original error if no field matches
                        raise
                except Exception:
                    raise  # Let validation errors bubble up
            else:
                raise  # Let validation errors bubble up
        
        logger.info("Parsed 1 model from text content")
        return [model]

    def write(self, models: List[BaseModel]) -> str:
        """Serialize model to plain text string.
        
        Args:
            models: List of Pydantic models (only first model used)
            
        Returns:
            Plain text string representation
            
        Raises:
            FileFormatError: If serialization fails
        """
        if not models:
            logger.debug("No models provided, returning empty text")
            return ""

        model = models[0]  # Only use first model for text
        if len(models) > 1:
            logger.warning("Multiple models provided to TXT writer, only using first model")

        logger.debug("Writing 1 model to text")

        try:
            data = model.model_dump(mode="json")
            
            # Try to extract text content from common field names
            for field_name in ['content', 'text', 'value', 'data']:
                if field_name in data and isinstance(data[field_name], str):
                    result = data[field_name]
                    break
            else:
                # If no text field found, convert entire model to string
                if len(data) == 1:
                    # Single field model - use the field value
                    value = next(iter(data.values()))
                    result = str(value) if value is not None else ""
                else:
                    # Multi-field model - use string representation
                    result = str(model)
                    
        except (TypeError, ValueError) as e:
            raise FileFormatError(f"Failed to serialize model to text: {e}") from e

        logger.info("Successfully serialized 1 model to text")
        return result

    def _model_allows_empty_content(self, model_class: Type[BaseModel]) -> bool:
        """Check if the model can handle empty content."""
        try:
            # Try to create model with empty content
            model_class.model_validate({'content': ''})
            return True
        except Exception:
            try:
                # Try other common patterns
                model_class.model_validate('')
                return True
            except Exception:
                return False