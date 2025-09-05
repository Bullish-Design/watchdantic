from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, List, Type, TypeVar, Any

try:
    import yaml
except ImportError:
    yaml = None

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # fallback for Python < 3.11

from pydantic import BaseModel

from watchdantic.exceptions import FileFormatError
from .base import FileFormatBase

logger = logging.getLogger("watchdantic.formats.markdown")
ModelT = TypeVar("ModelT", bound=BaseModel)


class MarkdownFile(FileFormatBase):
    """Handler for `.md` files - detects frontmatter and delegates appropriately."""

    def get_extension(self) -> str:
        return ".md"

    def read_models(self, file_path: Path, model_type: Type[ModelT]) -> List[ModelT]:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except IOError as exc:
            raise FileFormatError(f"Failed to read file {file_path}: {exc}") from exc

        return self.parse(content, model_type)

    def parse(self, content: str, model_class: Type[ModelT]) -> List[ModelT]:
        if not content.strip():
            logger.debug("Empty Markdown content, returning empty list")
            return []

        # Check for frontmatter and delegate if found
        if self._has_frontmatter(content):
            return self._parse_with_frontmatter(content, model_class)

        # Parse as plain markdown
        return self._parse_plain_markdown(content, model_class)

    def _has_frontmatter(self, content: str) -> bool:
        """Check if content has YAML or TOML frontmatter."""
        return content.startswith("---\n") or content.startswith("+++\n")

    def _parse_plain_markdown(self, content: str, model_class: Type[ModelT]) -> List[ModelT]:
        """Parse plain markdown without frontmatter."""
        model_fields = model_class.model_fields if hasattr(model_class, "model_fields") else {}

        try:
            if "content" in model_fields:
                model_data = {"content": content.strip()}
            else:
                # Try common field names for text content
                for field_name in ["text", "body", "markdown"]:
                    if field_name in model_fields:
                        model_data = {field_name: content.strip()}
                        break
                else:
                    # Single field model - use the content directly
                    if len(model_fields) == 1:
                        field_name = next(iter(model_fields.keys()))
                        model_data = {field_name: content.strip()}
                    else:
                        # Can't determine mapping
                        return []

            logger.debug(f"Validating markdown content with {model_class.__name__}")
            model = model_class.model_validate(model_data)
            logger.info("Parsed 1 model from plain Markdown content")
            return [model]

        except Exception:
            # Validation failed
            return []

    def _parse_with_frontmatter(self, content: str, model_class: Type[ModelT]) -> List[ModelT]:
        """Override in subclass for frontmatter support."""
        # Base class just treats it as plain markdown
        return self._parse_plain_markdown(content, model_class)

    def write(self, models: List[BaseModel]) -> str:
        if not models:
            logger.debug("No models provided, returning empty Markdown")
            return ""

        model = models[0]
        if len(models) > 1:
            logger.warning("Multiple models provided to Markdown writer, only using first model")

        logger.debug("Writing 1 model to Markdown")

        try:
            data = model.model_dump(mode="json")

            # Extract content from common field names
            for field_name in ["content", "text", "body", "markdown"]:
                if field_name in data and isinstance(data[field_name], str):
                    result = data[field_name]
                    break
            else:
                # Single field model - use the field value
                if len(data) == 1:
                    value = next(iter(data.values()))
                    result = str(value) if value is not None else ""
                else:
                    # Multi-field model - use string representation
                    result = str(model)

        except (TypeError, ValueError) as e:
            raise FileFormatError(f"Failed to serialize model to Markdown: {e}") from e

        logger.info("Successfully serialized 1 model to Markdown")
        return result


class MarkdownWithFrontmatter(MarkdownFile):
    """Handler for `.md` files with YAML/TOML frontmatter support."""

    def _parse_with_frontmatter(self, content: str, model_class: Type[ModelT]) -> List[ModelT]:
        """Parse markdown with frontmatter extraction."""
        frontmatter_data, body_content = self._extract_frontmatter(content)

        # Add body content if the model has a 'content' field
        model_fields = model_class.model_fields if hasattr(model_class, "model_fields") else {}
        if "content" in model_fields and body_content.strip():
            frontmatter_data["content"] = body_content.strip()

        if not frontmatter_data and not body_content.strip():
            return []

        try:
            logger.debug(f"Validating frontmatter data with {model_class.__name__}")
            model = model_class.model_validate(frontmatter_data)
            logger.info("Parsed 1 model from Markdown with frontmatter")
            return [model]
        except Exception:
            # Fall back to plain markdown parsing
            logger.debug(f"Frontmatter validation failed, trying plain markdown")
            return self._parse_plain_markdown(content, model_class)

    def write(self, models: List[BaseModel]) -> str:
        if not models:
            logger.debug("No models provided, returning empty Markdown")
            return ""

        if yaml is None:
            raise FileFormatError(
                "PyYAML package is required for writing Markdown files with frontmatter. "
                "Install with: pip install PyYAML"
            )

        model = models[0]
        if len(models) > 1:
            logger.warning("Multiple models provided to Markdown writer, only using first model")

        logger.debug("Writing 1 model to Markdown with frontmatter")

        try:
            data = model.model_dump(mode="json")

            # Extract content field if present
            content_body = ""
            if "content" in data:
                content_body = data.pop("content")

            # Check if there's meaningful metadata (non-empty, non-None values)
            has_metadata = any(value not in (None, "", []) for value in data.values())

            if has_metadata:
                frontmatter = yaml.dump(data, default_flow_style=False, allow_unicode=True)
                result = f"---\n{frontmatter}---\n\n{content_body}"
            else:
                result = content_body

        except (TypeError, ValueError) as e:
            raise FileFormatError(f"Failed to serialize model to Markdown: {e}") from e

        logger.info("Successfully serialized 1 model to Markdown")
        return result

    def _extract_frontmatter(self, content: str) -> tuple[Dict[str, Any], str]:
        # YAML frontmatter pattern (---)
        yaml_pattern = r"^---\s*\n(.*?)\n---\s*\n(.*)$"
        # TOML frontmatter pattern (+++)
        toml_pattern = r"^\+\+\+\s*\n(.*?)\n\+\+\+\s*\n(.*)$"

        yaml_match = re.match(yaml_pattern, content, re.DOTALL)
        if yaml_match:
            return self._parse_yaml_frontmatter(yaml_match.group(1)), yaml_match.group(2)

        toml_match = re.match(toml_pattern, content, re.DOTALL)
        if toml_match:
            return self._parse_toml_frontmatter(toml_match.group(1)), toml_match.group(2)

        # No frontmatter found
        return {}, content

    def _parse_yaml_frontmatter(self, frontmatter_text: str) -> Dict[str, Any]:
        if yaml is None:
            raise FileFormatError(
                "PyYAML package is required for parsing YAML frontmatter. Install with: pip install PyYAML"
            )

        try:
            data = yaml.safe_load(frontmatter_text)
            return data if isinstance(data, dict) else {}
        except yaml.YAMLError as e:
            raise FileFormatError(f"Invalid YAML frontmatter: {e}") from e

    def _parse_toml_frontmatter(self, frontmatter_text: str) -> Dict[str, Any]:
        try:
            return tomllib.loads(frontmatter_text)
        except tomllib.TOMLDecodeError as e:
            raise FileFormatError(f"Invalid TOML frontmatter: {e}") from e

