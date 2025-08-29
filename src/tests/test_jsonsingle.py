from __future__ import annotations

from pathlib import Path
from typing import List

import json
import pytest
from pydantic import BaseModel, ValidationError

from watchdantic.exceptions import FileFormatError
from watchdantic.formats.jsonsingle import JsonSingle


# Ignore the test model (pytest is picking it up as a test case):
import warnings

warnings.filterwarnings("ignore", message="cannot collect test class 'TestModel' because it has a __init__ constructor")


class TestModel(BaseModel):
    id: str
    value: int
    name: str = "default"


def test_get_extension() -> None:
    fmt = JsonSingle()
    assert fmt.get_extension() == ".json"


def test_parse_single_object(tmp_path: Path) -> None:
    content = {"id": "1", "value": 10}
    path = tmp_path / "single.json"
    path.write_text(json.dumps(content), encoding="utf-8")

    fmt = JsonSingle()
    result = fmt.parse(TestModel, path)

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].id == "1"
    assert result[0].value == 10
    assert result[0].name == "default"


def test_parse_array(tmp_path: Path) -> None:
    content = [{"id": "1", "value": 10}, {"id": "2", "value": 20}]
    path = tmp_path / "array.json"
    path.write_text(json.dumps(content), encoding="utf-8")

    fmt = JsonSingle()
    result = fmt.parse(TestModel, path)

    assert len(result) == 2
    assert [m.id for m in result] == ["1", "2"]
    assert [m.value for m in result] == [10, 20]


def test_parse_empty_array(tmp_path: Path) -> None:
    path = tmp_path / "empty.json"
    path.write_text("[]", encoding="utf-8")

    fmt = JsonSingle()
    result = fmt.parse(TestModel, path)
    assert result == []


def test_parse_invalid_json_raises_fileformaterror(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text('{"id": "1", "value":}', encoding="utf-8")

    fmt = JsonSingle()
    with pytest.raises(FileFormatError):
        fmt.parse(TestModel, path)


def test_parse_validation_error_bubbles(tmp_path: Path) -> None:
    # Missing required field 'id'
    path = tmp_path / "invalid_model.json"
    path.write_text(json.dumps({"value": 10}), encoding="utf-8")

    fmt = JsonSingle()
    with pytest.raises(ValidationError):
        fmt.parse(TestModel, path)


def test_write_single_model_is_object(tmp_path: Path) -> None:
    fmt = JsonSingle()
    path = tmp_path / "out.json"
    model = TestModel(id="1", value=10)

    fmt.write([model], path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert data["id"] == "1"
    assert data["value"] == 10


def test_write_multiple_models_is_array(tmp_path: Path) -> None:
    fmt = JsonSingle()
    path = tmp_path / "out.json"
    models: List[TestModel] = [
        TestModel(id="1", value=10),
        TestModel(id="2", value=20),
    ]

    fmt.write(models, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert [obj["id"] for obj in data] == ["1", "2"]


def test_write_empty_list_is_empty_array(tmp_path: Path) -> None:
    fmt = JsonSingle()
    path = tmp_path / "out.json"

    fmt.write([], path)
    assert path.read_text(encoding="utf-8") == "[]"


def test_round_trip(tmp_path: Path) -> None:
    fmt = JsonSingle()
    path = tmp_path / "round.json"
    models = [TestModel(id="1", value=10), TestModel(id="2", value=20)]

    # write
    fmt.write(models, path)

    # parse back
    parsed = fmt.parse(TestModel, path)
    assert [m.model_dump() for m in parsed] == [m.model_dump() for m in models]
