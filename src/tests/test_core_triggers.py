from pathlib import Path
from typing import List
import pytest
from pydantic import BaseModel

from watchdantic.core.watcher import Watchdantic
from watchdantic.core.config import WatchdanticConfig
from watchdantic.exceptions import ConfigurationError


class M(BaseModel):
    v: int


def test_triggers_on_registers_handler() -> None:
    w = Watchdantic(WatchdanticConfig(default_debounce=0.0))
    events = {}

    @w.triggers_on(M, "*.jsonl")
    def handle(items: List[M], file_path: Path) -> None:
        events["called"] = (len(items), file_path.suffix)

    # registry contains our handler name
    assert "handle" in w.registry.get_handler_names()


def test_triggers_on_signature_enforced() -> None:
    w = Watchdantic()

    # wrong param count
    with pytest.raises(ConfigurationError):

        @w.triggers_on(M, "*.jsonl")
        def bad(a: List[M]) -> None:  # type: ignore[no-redef]
            pass

    # wrong first param annotation
    with pytest.raises(ConfigurationError):

        @w.triggers_on(M, "*.jsonl")
        def bad2(a: List[int], file_path: Path) -> None:  # type: ignore[list-item]
            pass

    # wrong second param type
    with pytest.raises(ConfigurationError):

        @w.triggers_on(M, "*.jsonl")
        def bad3(a: List[M], file_path: str) -> None:  # type: ignore[arg-type]
            pass

    # wrong return type annotation
    with pytest.raises(ConfigurationError):

        @w.triggers_on(M, "*.jsonl")
        def bad4(a: List[M], file_path: Path) -> int:  # type: ignore[return-value]
            return 0
