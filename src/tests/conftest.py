from __future__ import annotations

import sys
from pathlib import Path
import pytest


@pytest.fixture(scope="session", autouse=True)
def add_src_to_path() -> None:
    """Ensure `src/` is importable during tests without installation."""
    root = Path(__file__).resolve().parent.parent
    src = root / "src"
    sys.path.insert(0, str(src))
