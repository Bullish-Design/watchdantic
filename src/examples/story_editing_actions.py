from __future__ import annotations

from pathlib import Path
from typing import List, Dict, Any, Set
import logging

from pydantic import BaseModel
from watchdantic import PipelineAction
from watchdantic.formats.jsonlines import JsonLines

from .models import (
    StoryText, ExampleNote, OutlineDoc, StoryDetailEnvelope, 
    UnreadableExample, ReplacementEntry, StoryProject, DraftManager
)
from .llms.outlines import decide_update_llm, generate_outline_llm, revise_outline_llm
from .llms.drafts import compose_draft_llm
from .llms.replacements import get_replacements_llm

logger = logging.getLogger("story_editing.actions")


class OutlineGeneratorAction(PipelineAction):
    """Generates or revises story outlines based on story.txt changes."""
    
    def __init__(self, root_path: Path):
        super().__init__("outline_generator")
        self.root_path = root_path
    
    def process(self, models: List[BaseModel], file_path: Path, context: Dict[str, Any]) -> List[tuple[Path, List[BaseModel]]]:
        story = models[0]
        story_id = file_path.parent.name
        proj = StoryProject.open(self.root_path, story_id)
        
        text = story.content.strip()
        outline_path = proj.outline_path
        
        if not outline_path.exists():
            logger.info(f"[{story_id}] Generating new outline")
            outline = generate_outline_llm(story_text=text)
            outline_path.parent.mkdir(parents=True, exist_ok=True)
            return [(outline_path, [outline])]
        
        logger.info(f"[{story_id}] Checking if outline needs revision")
        outline = proj.load_outline_toml()
        decision = decide_update_llm(
            existing_character_name=outline.character.name,
            existing_story_topic=outline.character.topic,
            existing_character_what=outline.character.what,
            existing_character_why=outline.character.why,
            existing_introduction=outline.plot_outline.introduction,
            existing_inciting_incident=outline.plot_outline.inciting_incident,
            existing_rising_action=outline.plot_outline.rising_action,
            existing_climax=outline.plot_outline.climax,
            existing_falling_action=outline.plot_outline.falling_action,
            existing_resolution=outline.plot_outline.resolution,
            existing_conclusion=outline.plot_outline.conclusion,
            story_text=text,
        )
        
        if getattr(decision, "update", False):
            logger.info(f"[{story_id}] Revising outline")
            updated = revise_outline_llm(
                character_name=outline.character.name,
                character_topic=outline.character.topic,
                character_what=outline.character.what,
                character_why=outline.character.why,
                introduction=outline.plot_outline.introduction,
                inciting_incident=outline.plot_outline.inciting_incident,
                rising_action=outline.plot_outline.rising_action,
                climax=outline.plot_outline.climax,
                falling_action=outline.plot_outline.falling_action,
                resolution=outline.plot_outline.resolution,
                conclusion=outline.plot_outline.conclusion,
                change_request=text,
            )
            return [(outline_path, [updated])]
        
        return []


class DraftComposerAction(PipelineAction):
    """Composes story drafts when outlines change."""
    
    def __init__(self, root_path: Path):
        super().__init__("draft_composer")
        self.root_path = root_path
    
    def process(self, models: List[BaseModel], file_path: Path, context: Dict[str, Any]) -> List[tuple[Path, List[BaseModel]]]:
        outline = models[0]
        story_id = file_path.parent.name
        proj = StoryProject.open(self.root_path, story_id)
        dm = DraftManager(project=proj)
        
        existing_text = proj.read_story_text() or ""
        logger.info(f"[{story_id}] Composing draft (context: {len(existing_text)} chars)")
        
        draft_text = compose_draft_llm(
            character_name=outline.character.name,
            character_topic=outline.character.topic,
            character_what=outline.character.what,
            character_why=outline.character.why,
            introduction=outline.plot_outline.introduction,
            inciting_incident=outline.plot_outline.inciting_incident,
            rising_action=outline.plot_outline.rising_action,
            climax=outline.plot_outline.climax,
            falling_action=outline.plot_outline.falling_action,
            resolution=outline.plot_outline.resolution,
            conclusion=outline.plot_outline.conclusion,
            existing_context=(
                f"EXISTING STORY CONTEXT:\n---\n{existing_text}\n---" if existing_text else ""
            ),
            change_note="",
        )
        
        dm.log_draft_from_text(source="outline_llm", outline=outline, story_text=str(draft_text))
        return []


class VocabularyCollectorAction(PipelineAction):
    """Collects unreadable words from story detail analysis."""
    
    def __init__(self, root_path: Path, vocab_root: Path):
        super().__init__("vocabulary_collector")
        self.root_path = root_path
        self.vocab_root = vocab_root
        self._jsonl = JsonLines()
    
    def process(self, models: List[BaseModel], file_path: Path, context: Dict[str, Any]) -> List[tuple[Path, List[BaseModel]]]:
        story_id = file_path.parent.parent.name
        proj = StoryProject.open(self.root_path, story_id)
        
        level = getattr(getattr(proj, "vocab", None), "level", None) or "UNKNOWN"
        
        words: Set[str] = set()
        for envelope in models:
            words.update(getattr(envelope.detail, "unreadable_unique_texts", []))
        
        if not words:
            logger.info(f"[{story_id}] No unreadables to add")
            return []
        
        out_dir = self.vocab_root / level
        out_dir.mkdir(parents=True, exist_ok=True)
        unreadables_path = out_dir / "unreadables.jsonl"
        
        existing = {u.word for u in self._read_jsonl(unreadables_path, UnreadableExample)}
        new_models = [UnreadableExample(word=w) for w in sorted(words - existing)]
        
        if not new_models:
            logger.info(f"[{story_id}] Unreadables already up-to-date for level {level}")
            return []
        
        logger.info(f"[{story_id}] Adding {len(new_models)} unreadables to {unreadables_path}")
        prior = self._read_jsonl(unreadables_path, UnreadableExample)
        return [(unreadables_path, prior + new_models)]
    
    def _read_jsonl(self, path: Path, model_cls) -> List[BaseModel]:
        if not path.exists():
            return []
        try:
            return self._jsonl.read_models(path, model_cls)
        except Exception as exc:
            logger.warning(f"Failed to read {path} as JSONL: {exc}")
            return []


class ReplacementProposerAction(PipelineAction):
    """Proposes word replacements when vocabulary lists change."""
    
    def __init__(self, vocab_root: Path):
        super().__init__("replacement_proposer")
        self.vocab_root = vocab_root
        self._jsonl = JsonLines()
    
    def process(self, models: List[BaseModel], file_path: Path, context: Dict[str, Any]) -> List[tuple[Path, List[BaseModel]]]:
        level_dir = file_path.parent
        repl_path = level_dir / "replacements.jsonl"
        
        existing_src = {r.source_word for r in self._read_jsonl(repl_path, ReplacementEntry)}
        new_words = sorted({u.word for u in models} - existing_src)
        
        if not new_words:
            logger.info(f"[vocab:{level_dir.name}] No new words for replacements")
            return []
        
        entries: List[ReplacementEntry] = []
        for word in new_words:
            ideas = get_replacements_llm(word=word)
            for cand in getattr(ideas, "words", []):
                entries.append(ReplacementEntry(source_word=word, replacement=cand))
        
        if not entries:
            logger.info(f"[vocab:{level_dir.name}] LLM returned no candidates")
            return []
        
        prior = self._read_jsonl(repl_path, ReplacementEntry)
        combined = self._unique_by_key(prior + entries, key=lambda r: f"{r.source_word}\u0000{r.replacement}")
        logger.info(f"[vocab:{level_dir.name}] Writing {len(combined) - len(prior)} replacement entries")
        return [(repl_path, combined)]
    
    def _read_jsonl(self, path: Path, model_cls) -> List[BaseModel]:
        if not path.exists():
            return []
        try:
            return self._jsonl.read_models(path, model_cls)
        except Exception as exc:
            logger.warning(f"Failed to read {path} as JSONL: {exc}")
            return []
    
    def _unique_by_key(self, items: List[BaseModel], key) -> List[BaseModel]:
        seen: Set[str] = set()
        out: List[BaseModel] = []
        for it in items:
            k = key(it)
            if k not in seen:
                seen.add(k)
                out.append(it)
        return out


class ExampleIndexerAction(PipelineAction):
    """Indexes example markdown files with front-matter."""
    
    def __init__(self, root_path: Path):
        super().__init__("example_indexer")
        self.root_path = root_path
        self._jsonl = JsonLines()
    
    def process(self, models: List[BaseModel], file_path: Path, context: Dict[str, Any]) -> List[tuple[Path, List[BaseModel]]]:
        idx_path = self.root_path / "examples.index.jsonl"
        prior = self._read_jsonl(idx_path)
        combined = self._unique_by_key(prior + models, key=lambda m: f"{m.title}\u0000{file_path}")
        return [(idx_path, combined)]
    
    def _read_jsonl(self, path: Path) -> List[BaseModel]:
        if not path.exists():
            return []
        try:
            return self._jsonl.read_models(path, ExampleNote)
        except Exception as exc:
            logger.warning(f"Failed to read {path} as JSONL: {exc}")
            return []
    
    def _unique_by_key(self, items: List[BaseModel], key) -> List[BaseModel]:
        seen: Set[str] = set()
        out: List[BaseModel] = []
        for it in items:
            k = key(it)
            if k not in seen:
                seen.add(k)
                out.append(it)
        return out
