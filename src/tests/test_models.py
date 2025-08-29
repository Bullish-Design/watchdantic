from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from watchdantic.core.models import WatchdanticConfig
from watchdantic.exceptions import ConfigurationError


def test_defaults_are_correct() -> None:
    cfg = WatchdanticConfig()
    assert cfg.log_level == "INFO"
    assert cfg.enable_logging is False
    assert cfg.log_file is None
    assert cfg.max_file_size == 100 * 1024 * 1024
    assert cfg.default_debounce == 1.0


@pytest.mark.parametrize(
    "log_level_in,log_level_expected",
    [
        ("INFO", "INFO"),
        ("DEBUG", "DEBUG"),
        ("WARN", "WARN"),
        ("ERROR", "ERROR"),
        # validator should normalize case:
        ("info", "INFO"),
        ("debug", "DEBUG"),
        ("warn", "WARN"),
        ("error", "ERROR"),
    ],
)
def test_valid_log_levels_and_normalization(log_level_in: str, log_level_expected: str) -> None:
    cfg = WatchdanticConfig(log_level=log_level_in)
    assert cfg.log_level == log_level_expected


def test_custom_values_are_accepted(tmp_path: Path) -> None:
    log_path = tmp_path / "logs" / "watchdantic.jsonl"
    # We only assert the path value; file does not need to exist.
    cfg = WatchdanticConfig(
        log_level="DEBUG",
        enable_logging=True,
        log_file=log_path,
        max_file_size=10 * 1024 * 1024,
        default_debounce=0.25,
    )
    assert cfg.log_level == "DEBUG"
    assert cfg.enable_logging is True
    assert cfg.log_file == log_path
    assert cfg.max_file_size == 10 * 1024 * 1024
    assert cfg.default_debounce == 0.25


@pytest.mark.parametrize("bad_level", ["", "trace", "information", "warning", "fatal", "VERBOSE"])
def test_invalid_log_level_raises_validation_error(bad_level: str) -> None:
    with pytest.raises(ValidationError) as ei:
        WatchdanticConfig(log_level=bad_level)
    # Helpful assertion so failures show which bad level failed
    assert "log_level" in str(ei.value).lower()


@pytest.mark.parametrize("size", [0, -1, -100])
def test_non_positive_file_size_raises_validation_error(size: int) -> None:
    with pytest.raises(ValidationError) as ei:
        WatchdanticConfig(max_file_size=size)
    assert "max_file_size" in str(ei.value).lower()


@pytest.mark.parametrize("debounce", [-0.00001, -1, -5.5])
def test_negative_debounce_raises_validation_error(debounce: float) -> None:
    with pytest.raises(ValidationError) as ei:
        WatchdanticConfig(default_debounce=debounce)
    assert "default_debounce" in str(ei.value).lower()


def test_optional_log_file_none_when_logging_disabled_is_ok() -> None:
    cfg = WatchdanticConfig(enable_logging=False, log_file=None)
    assert cfg.log_file is None
    assert cfg.enable_logging is False


def test_enable_logging_requires_log_file(tmp_path: Path) -> None:
    # When enable_logging=True and log_file is None, we expect a ConfigurationError
    with pytest.raises(ConfigurationError):
        WatchdanticConfig(enable_logging=True, log_file=None)

    # But providing a path should be fine
    cfg = WatchdanticConfig(enable_logging=True, log_file=tmp_path / "log.jsonl")
    assert cfg.enable_logging is True
    assert isinstance(cfg.log_file, Path)


def test_model_is_frozen_immutable(tmp_path: Path) -> None:
    cfg = WatchdanticConfig(log_file=tmp_path / "log.jsonl")
    # Pydantic v2 typically raises ValidationError(type=frozen_instance) on frozen assignment,
    # but accept TypeError too to be robust across environments.
    with pytest.raises((TypeError, ValidationError)):
        cfg.log_level = "ERROR"  # type: ignore[attr-defined]


def test_field_descriptions_present() -> None:
    fields = WatchdanticConfig.model_fields

    # Ensure every required field has a description per spec
    for name in ("log_level", "enable_logging", "log_file", "max_file_size", "default_debounce"):
        assert name in fields, f"Field '{name}' missing from model_fields"
        desc = fields[name].description
        assert isinstance(desc, str) and desc.strip(), f"Missing/empty description for '{name}'"
