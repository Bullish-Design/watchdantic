#!/usr/bin/env python3
# /// script
# dependencies = [
#     "watchdantic>=0.3.0",
#     "pydantic>=2.0.0",
#     "PyYAML>=6.0.0",
#     "tomli>=2.0.0; python_version < '3.11'",
#     "tomli_w>=1.0.0",
# ]
# ///
"""
Story Editing Workflow using Integrated Watchdantic Pipeline Framework

Demonstrates the updated watchdantic with built-in pipeline support:
- PipelineBuilder and PipelineAction are now core watchdantic classes
- Story-specific actions are separate plugin modules
- Cleaner separation of concerns and better reusability

Usage:
    uv run examples/editing_workflow.py
"""
from __future__ import annotations

import os
import logging
from pathlib import Path

from watchdantic import PipelineBuilder, WatchdanticConfig, TriggerConfig
from story_editing.actions import (
    OutlineGeneratorAction, DraftComposerAction, VocabularyCollectorAction,
    ReplacementProposerAction, ExampleIndexerAction
)
from story_editing.models import (
    StoryText, ExampleNote, OutlineDoc, StoryDetailEnvelope, UnreadableExample
)

logger = logging.getLogger("editing_workflow")
logger.setLevel(logging.INFO)

ROOT = Path(os.environ.get("STORIES_ROOT", "stories")).resolve()
VOCAB_ROOT = Path(os.environ.get("VOCAB_ROOT", ROOT / "vocab")).resolve()


def create_editing_pipeline() -> PipelineBuilder:
    """Create the complete story editing pipeline."""
    
    config = WatchdanticConfig(
        default_debounce=1.0,
        enable_logging=False,
        recursive=True
    )
    
    return (PipelineBuilder(config)
        .set_context(root_path=ROOT, vocab_root=VOCAB_ROOT)
        
        # Story text changes trigger outline generation/revision
        .add_trigger(TriggerConfig(
            name="ensure_outline",
            pattern="**/*/story.txt",
            model_class=StoryText,
            action_instance=OutlineGeneratorAction(ROOT),
            debounce=1.0
        ))
        
        # Outline changes trigger draft composition
        .add_trigger(TriggerConfig(
            name="draft_on_outline", 
            pattern="**/*/outline.toml",
            model_class=OutlineDoc,
            action_instance=DraftComposerAction(ROOT),
            debounce=1.0
        ))
        
        # Story analysis triggers vocabulary collection
        .add_trigger(TriggerConfig(
            name="collect_unreadables",
            pattern="**/*/revisions/storydetail.jsonl",
            model_class=StoryDetailEnvelope,
            action_instance=VocabularyCollectorAction(ROOT, VOCAB_ROOT),
            debounce=1.0
        ))
        
        # Vocabulary changes trigger replacement proposals
        .add_trigger(TriggerConfig(
            name="propose_replacements",
            pattern=str(VOCAB_ROOT / "*" / "unreadables.jsonl"),
            model_class=UnreadableExample,
            action_instance=ReplacementProposerAction(VOCAB_ROOT),
            debounce=1.0,
            recursive=False
        ))
        
        # Example markdown files trigger indexing
        .add_trigger(TriggerConfig(
            name="index_examples",
            pattern="examples/**/*.md", 
            model_class=ExampleNote,
            action_instance=ExampleIndexerAction(ROOT),
            debounce=1.0
        ))
        
        .build()
    )


def main() -> None:
    """Main entry point for story editing workflow."""
    
    ROOT.mkdir(parents=True, exist_ok=True)
    VOCAB_ROOT.mkdir(parents=True, exist_ok=True)
    
    pipeline = create_editing_pipeline()
    
    logger.info(f"Starting editing workflow at {ROOT} (vocab: {VOCAB_ROOT})")
    logger.info(f"Pipeline configured with {len(pipeline.triggers)} triggers")
    
    try:
        pipeline.start(ROOT)
        
        import time
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Shutting down editing workflow...")
        pipeline.stop()
        logger.info("Workflow stopped")


if __name__ == "__main__":
    main()
