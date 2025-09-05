from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict, Any, Type, Optional
from dataclasses import dataclass
import logging

from pydantic import BaseModel

logger = logging.getLogger("watchdantic.actions")


class PipelineAction(ABC):
    """Base class for reusable pipeline actions that process file changes."""
    
    def __init__(self, name: str):
        self.name = name
    
    @abstractmethod
    def process(
        self, 
        models: List[BaseModel], 
        file_path: Path, 
        context: Dict[str, Any]
    ) -> List[tuple[Path, List[BaseModel]]]:
        """
        Process input models and return list of (output_path, models) to write.
        
        Args:
            models: Input models parsed from the triggering file
            file_path: Path of the file that triggered this action
            context: Shared workflow context dictionary
            
        Returns:
            List of (output_path, output_models) tuples to write atomically.
            Empty list means no file outputs (side effects only).
        """
        pass
    
    def on_error(self, error: Exception, models: List[BaseModel], file_path: Path) -> bool:
        """
        Handle processing errors.
        
        Args:
            error: The exception that occurred
            models: The input models being processed
            file_path: Path that triggered the action
            
        Returns:
            True to continue processing other actions, False to stop pipeline
        """
        logger.error(f"Error in action {self.name}: {error}")
        return True


@dataclass
class TriggerConfig:
    """Configuration for a pipeline trigger and its associated action."""
    
    name: str
    pattern: str
    model_class: Type[BaseModel] 
    action_instance: PipelineAction
    debounce: float = 0.5
    continue_on_error: bool = True
    recursive: bool = True
    exclude_patterns: Optional[List[str]] = None
