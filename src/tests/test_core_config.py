from pathlib import Path
import pytest
from pydantic import ValidationError

from watchdantic.core.config import WatchdanticConfig


def test_config_defaults_and_frozen(tmp_path: Path) -> None:
    cfg = WatchdanticConfig()
    assert cfg.default_debounce == 1.0
    assert cfg.recursive is True
    assert cfg.enable_logging is False
    assert cfg.max_bytes == cfg.max_file_size_mb * 1024 * 1024

    # frozen/immutable - Pydantic v2 raises a ValidationError
    with pytest.raises(ValidationError):
        cfg.default_debounce = 2.0  # type: ignore


def test_config_log_level_validation() -> None:
    # valid
    for lvl in ("debug", "INFO", "Warning", "ERROR", "CRITICAL"):
        assert WatchdanticConfig(log_level=lvl).log_level == lvl.upper()

    # invalid
    with pytest.raises(ValueError):
        WatchdanticConfig(log_level="NOPE")
