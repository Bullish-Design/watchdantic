"""
Editing workflow powered by Watchdantic.

This single runtime recreates the prior story_editing watch_* scripts:
- ensure_outline: reacts to **/story.txt → create/decide/revise outline.toml
- draft_on_outline: reacts to **/outline.toml → compose and log a new draft
- collect_unreadables: reacts to **/revisions/storydetail.jsonl → update vocab/*/unreadables.jsonl
- propose_replacements: reacts to vocab/*/*/unreadables.jsonl → write replacements.jsonl candidates
- (optional) index_examples: reacts to examples/**/*.md (front-matter + body)

Place this file at: src/examples/editing_workflow.py
Run directly or import the handlers into your own runner.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Iterable, Set
import os
import logging

from pydantic import BaseModel

# Watchdantic core
from watchdantic import Watchdantic
from watchdantic.core.models import WatchdanticConfig  # adjust if your path differs
# Optional direct format helpers (only used for JSONL readbacks)
from watchdantic.formats.jsonlines import JsonLines

# --- Project (story_editing) imports: adjust module paths to your repo structure ---
from story_editing.models.story_models import (
    OutlineDoc,
    StoryDetailEnvelope,
    UnreadableExample,
    ReplacementEntry,
    ReplacementIdeas,
    StoryProject,
    DraftManager,
)
from story_editing.llms.outlines import (
    decide_update_llm,
    generate_outline_llm,
    revise_outline_llm,
)
from story_editing.llms.drafts import compose_draft_llm
from story_editing.llms.replacements import get_replacements_llm


# --------------------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------------------
logger = logging.getLogger("editing_workflow")
logger.setLevel(logging.INFO)

# Root of stories and vocab; can be overridden by env vars
ROOT = Path(os.environ.get("STORIES_ROOT", "stories")).resolve()
VOCAB_ROOT = Path(os.environ.get("VOCAB_ROOT", ROOT / "vocab")).resolve()

# Watchdantic instance (tune config as needed in your repo)
w = Watchdantic(WatchdanticConfig(debounce_seconds=1.0))


# --------------------------------------------------------------------------------------
# Lightweight adapter models for non-structured files
# --------------------------------------------------------------------------------------
class StoryText(BaseModel):
    """Adapter for plain text files; entire file becomes `content`."""
    content: str = ""


class ExampleNote(BaseModel):
    """Optional: front-matter + Markdown body to index examples.

    Expect front-matter fields like:
    ---
    title: "Example title"
    tags: ["tag1", "tag2"]
    ---
    (body...)
    """
    title: str | None = None
    tags: list[str] = []
    content: str = ""  # markdown body (no front-matter)


# --------------------------------------------------------------------------------------
# Utilities
# --------------------------------------------------------------------------------------
_jl = JsonLines()

def _read_jsonl(path: Path, model_cls) -> List[BaseModel]:
    if not path.exists():
        return []
    try:
        return _jl.read_models(path, model_cls)
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("Failed to read %s as JSONL: %s", path, exc)
        return []


def _unique_by_key(items: Iterable[BaseModel], key) -> List[BaseModel]:
    seen: Set[str] = set()
    out: list[BaseModel] = []
    for it in items:
        k = key(it)
        if k not in seen:
            seen.add(k)
            out.append(it)
    return out


# --------------------------------------------------------------------------------------
# 1) Ensure/Decide/Revise Outline from story.txt
# --------------------------------------------------------------------------------------
@w.handler(StoryText, pattern="**/*/story.txt", debounce=1.0)
def ensure_outline(models: List[StoryText], file_path: Path) -> None:
    story_id = file_path.parent.name
    proj = StoryProject.open(ROOT, story_id)

    text = (models[0].content or "").strip()
    outline_path = proj.outline_path  # expected <story>/outline.toml

    if not outline_path.exists():
        logger.info("[%s] outline missing → generating", story_id)
        outline = generate_outline_llm(story_text=text)
        outline_path.parent.mkdir(parents=True, exist_ok=True)
        w.write_models([outline], outline_path)
        return

    logger.info("[%s] outline exists → deciding whether to revise", story_id)
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
        logger.info("[%s] revising outline", story_id)
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
        w.write_models([updated], outline_path)


# --------------------------------------------------------------------------------------
# 2) Compose and log a draft when outline.toml changes
# --------------------------------------------------------------------------------------
@w.handler(OutlineDoc, pattern="**/*/outline.toml", debounce=1.0)
def draft_on_outline(models: List[OutlineDoc], outline_path: Path) -> None:
    outline = models[0]
    story_id = outline_path.parent.name
    proj = StoryProject.open(ROOT, story_id)
    dm = DraftManager(project=proj)

    existing_text = proj.read_story_text() or ""
    logger.info("[%s] composing draft from outline (existing context: %s chars)", story_id, len(existing_text))

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


# --------------------------------------------------------------------------------------
# 3) Collect unreadables from revisions/storydetail.jsonl into vocab/*/unreadables.jsonl
# --------------------------------------------------------------------------------------
@w.handler(StoryDetailEnvelope, pattern="**/*/revisions/storydetail.jsonl", debounce=1.0)
def collect_unreadables(envelopes: List[StoryDetailEnvelope], detail_path: Path) -> None:
    story_id = detail_path.parent.parent.name  # <story>/revisions/
    proj = StoryProject.open(ROOT, story_id)

    # Prefer whatever your StoryProject exposes for level; keep a sensible fallback
    level = getattr(getattr(proj, "vocab", None), "level", None) or "UNKNOWN"

    words: set[str] = set()
    for env in envelopes:
        # attribute name may differ in your model; adjust if needed
        words.update(getattr(env.detail, "unreadable_unique_texts", []))

    if not words:
        logger.info("[%s] no unreadables to add", story_id)
        return

    out_dir = VOCAB_ROOT / level
    out_dir.mkdir(parents=True, exist_ok=True)
    unreadables_path = out_dir / "unreadables.jsonl"

    existing = {u.word for u in _read_jsonl(unreadables_path, UnreadableExample)}
    new_models = [UnreadableExample(word=w) for w in sorted(words - existing)]

    if not new_models:
        logger.info("[%s] unreadables already up-to-date for level %s", story_id, level)
        return

    logger.info("[%s] adding %d unreadables to %s", story_id, len(new_models), unreadables_path)
    prior = _read_jsonl(unreadables_path, UnreadableExample)
    w.write_models(prior + new_models, unreadables_path)


# --------------------------------------------------------------------------------------
# 4) Propose replacements when unreadables.jsonl changes
# --------------------------------------------------------------------------------------
@w.handler(UnreadableExample, pattern=str(VOCAB_ROOT / "*" / "unreadables.jsonl"), debounce=1.0, recursive=False)
def propose_replacements(items: List[UnreadableExample], unreadables_path: Path) -> None:
    level_dir = unreadables_path.parent
    repl_path = level_dir / "replacements.jsonl"

    # Avoid re-suggesting for words that already have entries
    existing_src = {r.source_word for r in _read_jsonl(repl_path, ReplacementEntry)}
    new_words = sorted({u.word for u in items} - existing_src)

    if not new_words:
        logger.info("[vocab:%s] no new words for replacements", level_dir.name)
        return

    entries: list[ReplacementEntry] = []
    for word in new_words:
        ideas: ReplacementIdeas = get_replacements_llm(word=word)
        # Assume `ideas.words` contains a list[str] of candidate replacements
        for cand in getattr(ideas, "words", []):
            entries.append(ReplacementEntry(source_word=word, replacement=cand))

    if not entries:
        logger.info("[vocab:%s] LLM returned no candidates", level_dir.name)
        return

    prior = _read_jsonl(repl_path, ReplacementEntry)
    # de-dup by (source_word, replacement)
    combined = _unique_by_key(prior + entries, key=lambda r: f"{r.source_word}\u0000{r.replacement}")
    logger.info("[vocab:%s] writing %d replacement entries", level_dir.name, len(combined) - len(prior))
    w.write_models(combined, repl_path)


# --------------------------------------------------------------------------------------
# (Optional) Index examples from Markdown with front-matter
# --------------------------------------------------------------------------------------
@w.handler(ExampleNote, pattern="examples/**/*.md", debounce=1.0)
def index_examples(models: List[ExampleNote], file_path: Path) -> None:  # pragma: no cover — optional
    idx_path = ROOT / "examples.index.jsonl"
    prior = _read_jsonl(idx_path, ExampleNote)
    combined = _unique_by_key(prior + models, key=lambda m: f"{m.title}\u0000{file_path}")
    w.write_models(combined, idx_path)


# --------------------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------------------
if __name__ == "__main__":
    ROOT.mkdir(parents=True, exist_ok=True)
    VOCAB_ROOT.mkdir(parents=True, exist_ok=True)
    logger.info("Starting editing workflow watcher at %s (vocab: %s)", ROOT, VOCAB_ROOT)
    w.start(ROOT)
