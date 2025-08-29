from __future__ import annotations

import logging
from typing import List

import pytest
from pydantic import BaseModel, ValidationError

from watchdantic.formats.jsonlines import JsonLines

# Ignore the test model (pytest is picking it up as a test case):
import warnings

warnings.filterwarnings("ignore", message="cannot collect test class 'TestModel' because it has a __init__ constructor")


class TestModel(BaseModel):
    id: str
    value: int
    name: str = "default"


@pytest.fixture(autouse=True)
def _setup_logging(caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.WARNING)


def test_get_extension() -> None:
    assert JsonLines().get_extension() == ".jsonl"


def test_parse_valid_content() -> None:
    content = "\n".join(
        [
            '{"id": "1", "value": 10}',
            '{"id": "2", "value": 20, "name": "custom"}',
        ]
    )
    models = JsonLines().parse(content, TestModel)
    assert [m.id for m in models] == ["1", "2"]
    assert models[0].name == "default"
    assert models[1].name == "custom"


def test_parse_skips_empty_and_whitespace_lines() -> None:
    content = "\n".join(
        [
            "",
            "   ",
            '{"id": "3", "value": 30}',
            "\t",
        ]
    )
    models = JsonLines().parse(content, TestModel)
    assert len(models) == 1
    assert models[0].id == "3"


def test_parse_skips_invalid_json_lines(caplog: pytest.LogCaptureFixture) -> None:
    content = "\n".join(
        [
            '{"id": "3", "value": 30}',
            "invalid json line",
            '{"id": "4", "value": 40}',
        ]
    )
    models = JsonLines().parse(content, TestModel)
    assert [m.id for m in models] == ["3", "4"]
    # Ensure a warning was logged for the invalid line
    assert any("Skipping invalid JSON line" in rec.message for rec in caplog.records)


def test_parse_validation_error_bubbles_up() -> None:
    # missing required field 'value'
    content = '{"id": "x"}'
    with pytest.raises(ValidationError):
        JsonLines().parse(content, TestModel)


def test_write_single_model() -> None:
    txt = JsonLines().write([TestModel(id="1", value=10)])
    assert txt == '{"id":"1","value":10,"name":"default"}\n'


def test_write_multiple_models() -> None:
    models: List[TestModel] = [
        TestModel(id="1", value=10),
        TestModel(id="2", value=20, name="custom"),
    ]
    txt = JsonLines().write(models)
    assert txt == ('{"id":"1","value":10,"name":"default"}\n' + '{"id":"2","value":20,"name":"custom"}\n')


def test_write_empty_list() -> None:
    assert JsonLines().write([]) == "\n"


def test_round_trip_parse_then_write() -> None:
    content = "\n".join(
        [
            '{"id": "1", "value": 10}',
            '{"id": "2", "value": 20, "name": "custom"}',
            "",
            '{"id": "3", "value": 30}',
            "invalid json line",
            '{"id": "4", "value": 40}',
        ]
    )
    models = JsonLines().parse(content, TestModel)
    txt = JsonLines().write(models)
    # Ensure every parsed model appears exactly once after writing
    assert txt == (
        '{"id":"1","value":10,"name":"default"}\n'
        '{"id":"2","value":20,"name":"custom"}\n'
        '{"id":"3","value":30,"name":"default"}\n'
        '{"id":"4","value":40,"name":"default"}\n'
    )
