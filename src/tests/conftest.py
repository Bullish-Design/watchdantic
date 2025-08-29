# Ensures pytest can import tests as "tests.*" when they live under src/tests,
# and avoids collecting archived v1 tests. Also mutes watchdantic logs.

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any
import warnings

import pytest
from _pytest.warning_types import PytestCollectionWarning

# --- Suppress noisy "cannot collect test class 'TestModel'..." warnings ---
warnings.filterwarnings(
    "ignore",
    category=PytestCollectionWarning,
    message=r".*cannot collect test class 'TestModel'.*",
)

"""
@pytest.fixture(scope="session", autouse=True)
def add_src_to_path() -> None:
    '''Ensure `src/` is importable during tests without installation.'''
    root = Path(__file__).resolve().parent.parent
    src = root / "src"
    sys.path.insert(0, str(src))
"""

# --- Make "src" importable so "tests.*" resolves during package-mode import ---
SRC_DIR = Path(__file__).resolve().parents[1]  # .../src
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

"""
# Quiet watchdantic logger by default
@pytest.fixture(autouse=True)
def _mute_watchdantic_logger() -> Any:
    logger = logging.getLogger("watchdantic")
    prev = logger.level
    logger.setLevel(logging.CRITICAL)
    try:
        yield
    finally:
        logger.setLevel(prev or logging.WARNING)
"""

# Suppress noisy Pydantic TestModel collection warning
warnings.filterwarnings(
    "ignore",
    category=PytestCollectionWarning,
    message=r".*cannot collect test class 'TestModel'.*",
)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "core: core functionality tests")


# Updated hook signature for pytest ≥8 (uses collection_path: pathlib.Path)
def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool:  # type: ignore[override]
    p = str(collection_path)
    return "/src/archive/" in p or p.endswith("/src/archive") or "src/archive/" in p


"""
# --- Skip archived/legacy tests under src/archive to keep the run minimal ---
def pytest_ignore_collect(path: Path, config: pytest.Config) -> bool:  # type: ignore[override]
    # Normalize to string for robust matching across path types
    p = str(path)
    # Ignore everything under src/archive (legacy test copies, snapshots, etc.)
    return "/src/archive/" in p or p.endswith("/src/archive") or "src/archive/" in p



# --- Keep logs quiet by default during tests ---
@pytest.fixture(autouse=True)
def _mute_watchdantic_logger() -> Any:
    logger = logging.getLogger("watchdantic")
    prev_level = logger.level
    logger.setLevel(logging.CRITICAL)
    try:
        yield
    finally:
        logger.setLevel(prev_level or logging.WARNING)
        """
