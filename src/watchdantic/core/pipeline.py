from __future__ import annotations

from pathlib import Path
from typing import List, Dict, Any, Optional
import logging

from pydantic import BaseModel

from .watcher import Watchdantic
from .config import WatchdanticConfig
from .actions import PipelineAction, TriggerConfig

logger = logging.getLogger("watchdantic.pipeline")


class PipelineBuilder:
    """Builds and manages event-driven workflows using Watchdantic and pipeline actions."""
    
    def __init__(self, config: Optional[WatchdanticConfig] = None):
        """Initialize pipeline builder with optional configuration."""
        self.watchdantic = Watchdantic(config or WatchdanticConfig())
        self.context: Dict[str, Any] = {}
        self.triggers: List[TriggerConfig] = []
    
    def add_trigger(self, config: TriggerConfig) -> 'PipelineBuilder':
        """Add a trigger configuration to the pipeline."""
        self.triggers.append(config)
        return self
    
    def set_context(self, **kwargs: Any) -> 'PipelineBuilder':
        """Set shared context variables accessible to all actions."""
        self.context.update(kwargs)
        return self
    
    def build(self) -> 'PipelineBuilder':
        """Build all Watchdantic handlers from trigger configurations."""
        for trigger in self.triggers:
            
            def make_handler(action: PipelineAction, config: TriggerConfig):
                """Create a Watchdantic handler function for the given action."""
                
                def handler(models: List[BaseModel], file_path: Path) -> None:
                    try:
                        logger.info(f"Executing action {action.name} for {file_path}")
                        outputs = action.process(models, file_path, self.context)
                        
                        # Write all outputs atomically
                        for output_path, output_models in outputs:
                            if output_models:
                                logger.info(f"Writing {len(output_models)} models to {output_path}")
                                self.watchdantic.write_models(output_models, output_path)
                        
                    except Exception as e:
                        should_continue = action.on_error(e, models, file_path)
                        if not (should_continue and config.continue_on_error):
                            raise
                
                return handler
            
            # Register handler with Watchdantic using the triggers_on decorator
            self.watchdantic.triggers_on(
                trigger.model_class,
                trigger.pattern,
                debounce=trigger.debounce,
                continue_on_error=trigger.continue_on_error,
                recursive=trigger.recursive,
                exclude_patterns=trigger.exclude_patterns or []
            )(make_handler(trigger.action_instance, trigger))
        
        return self
    
    def start(self, watch_path: Path) -> None:
        """Start the pipeline, watching the specified path."""
        logger.info(f"Starting pipeline with {len(self.triggers)} triggers, watching {watch_path}")
        self.watchdantic.start(watch_path)
    
    def stop(self) -> None:
        """Stop the pipeline and clean up resources."""
        logger.info("Stopping pipeline")
        self.watchdantic.stop()
    
    def write_models(self, models: List[BaseModel], path: Path) -> None:
        """Write models atomically (convenience method for external use)."""
        self.watchdantic.write_models(models, path)
    
    @property
    def steps(self) -> List[TriggerConfig]:
        """Alias for triggers (backward compatibility)."""
        return self.triggers
