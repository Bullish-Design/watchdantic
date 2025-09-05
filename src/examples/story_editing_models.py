from __future__ import annotations

from pathlib import Path
from typing import List

from pydantic import BaseModel

# Re-export main story editing models (adjust import paths as needed)
from story_editing.models.story_models import (
    OutlineDoc, StoryProject, DraftManager, 
    StoryDetailEnvelope, UnreadableExample, ReplacementEntry
)

# Adapter models for Watchdantic file processing
class StoryText(BaseModel):
    """Adapter for plain text story files; entire file becomes content field."""
    content: str = ""


class ExampleNote(BaseModel):
    """Adapter for markdown files with front-matter.
    
    Expected front-matter format:
    ---
    title: "Example title"
    tags: ["tag1", "tag2"]
    ---
    (markdown body content)
    """
    title: str | None = None
    tags: List[str] = []
    content: str = ""


__all__ = [
    "StoryText",
    "ExampleNote", 
    "OutlineDoc",
    "StoryProject",
    "DraftManager",
    "StoryDetailEnvelope",
    "UnreadableExample", 
    "ReplacementEntry"
]
