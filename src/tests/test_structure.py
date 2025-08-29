from __future__ import annotations


def test_can_import_top_level():
    import watchdantic  # noqa: F401


def test_can_import_core_modules():
    import watchdantic.core.watcher  # noqa: F401
    import watchdantic.core.models  # noqa: F401


def test_can_import_format_modules():
    import watchdantic.formats.base  # noqa: F401
    import watchdantic.formats.jsonlines  # noqa: F401
    import watchdantic.formats.jsonsingle  # noqa: F401


def test_can_import_exceptions():
    import watchdantic.exceptions as exc  # noqa: F401

    # The placeholder keeps the module non-empty; adjust once exceptions exist.
    assert hasattr(exc, "_Placeholder")
