from __future__ import annotations

import pytest
from pathlib import Path
from typing import List
from pydantic import BaseModel

from watchdantic.core.watcher import WatchdanticCore
from watchdantic.exceptions import ConfigurationError


# Ignore the test model (pytest is picking it up as a test case):
import warnings

warnings.filterwarnings("ignore", message="cannot collect test class 'TestModel' because it has a __init__ constructor")


class TestModel(BaseModel):
    id: str
    value: int


class AlternativeModel(BaseModel):
    name: str
    count: int


def test_valid_handler_signatures():
    """Test that valid handler signatures pass validation."""
    watcher = WatchdanticCore()

    # Test with typing.List
    @watcher.triggers_on(TestModel, "*.jsonl")
    def handler_with_typing_list(models: List[TestModel], file_path: Path) -> None:
        pass

    # Test with builtin list (Python 3.9+)
    @watcher.triggers_on(TestModel, "*.jsonl")
    def handler_with_builtin_list(models: list[TestModel], file_path: Path) -> None:
        pass

    # Test without explicit return annotation
    @watcher.triggers_on(TestModel, "*.jsonl")
    def handler_no_return_annotation(models: List[TestModel], file_path: Path):
        pass

    # All should be registered successfully
    assert "handler_with_typing_list" in watcher.registry.get_handler_names()
    assert "handler_with_builtin_list" in watcher.registry.get_handler_names()
    assert "handler_no_return_annotation" in watcher.registry.get_handler_names()


def test_invalid_parameter_types():
    """Test that invalid parameter types raise ConfigurationError."""
    watcher = WatchdanticCore()

    # Wrong first parameter type (not List)
    with pytest.raises(ConfigurationError, match="first parameter must be annotated as List"):

        @watcher.triggers_on(TestModel, "*.jsonl")
        def bad_handler_single_model(models: TestModel, file_path: Path) -> None:
            pass

    # Wrong second parameter type (not Path)
    with pytest.raises(ConfigurationError, match="second parameter must be annotated as pathlib.Path"):

        @watcher.triggers_on(TestModel, "*.jsonl")
        def bad_handler_str_path(models: List[TestModel], file_path: str) -> None:
            pass

    # Wrong first parameter type (dict instead of List)
    with pytest.raises(ConfigurationError, match="first parameter must be annotated as List"):

        @watcher.triggers_on(TestModel, "*.jsonl")
        def bad_handler_dict(models: dict, file_path: Path) -> None:
            pass


def test_missing_type_annotations():
    """Test that missing type annotations raise ConfigurationError."""
    watcher = WatchdanticCore()

    # No annotations at all
    with pytest.raises(ConfigurationError, match="first parameter must be annotated"):

        @watcher.triggers_on(TestModel, "*.jsonl")
        def no_annotations(models, file_path):
            pass

    # Missing first parameter annotation
    with pytest.raises(ConfigurationError, match="first parameter must be annotated"):

        @watcher.triggers_on(TestModel, "*.jsonl")
        def missing_first_annotation(models, file_path: Path) -> None:
            pass

    # Missing second parameter annotation
    with pytest.raises(ConfigurationError, match="second parameter must be annotated as pathlib.Path"):

        @watcher.triggers_on(TestModel, "*.jsonl")
        def missing_second_annotation(models: List[TestModel], file_path) -> None:
            pass


def test_incorrect_model_types():
    """Test that incorrect model types in annotations raise ConfigurationError."""
    watcher = WatchdanticCore()

    # Wrong model class in List annotation
    with pytest.raises(ConfigurationError, match="first parameter must be annotated as List\\[TestModel\\]"):

        @watcher.triggers_on(TestModel, "*.jsonl")
        def wrong_model_handler(models: List[AlternativeModel], file_path: Path) -> None:
            pass

    # List without type parameter
    with pytest.raises(ConfigurationError, match="first parameter must be annotated as List\\[TestModel\\]"):

        @watcher.triggers_on(TestModel, "*.jsonl")
        def bare_list_handler(models: List, file_path: Path) -> None:
            pass


def test_return_type_validation():
    """Test return type validation."""
    watcher = WatchdanticCore()

    # Valid return type annotations
    @watcher.triggers_on(TestModel, "*.jsonl")
    def handler_explicit_none(models: List[TestModel], file_path: Path) -> None:
        pass

    @watcher.triggers_on(TestModel, "*.jsonl")
    def handler_no_annotation(models: List[TestModel], file_path: Path):
        pass

    # Invalid return types
    with pytest.raises(ConfigurationError, match="handler must return None"):

        @watcher.triggers_on(TestModel, "*.jsonl")
        def handler_int_return(models: List[TestModel], file_path: Path) -> int:
            return 42

    with pytest.raises(ConfigurationError, match="handler must return None"):

        @watcher.triggers_on(TestModel, "*.jsonl")
        def handler_str_return(models: List[TestModel], file_path: Path) -> str:
            return "result"

    with pytest.raises(ConfigurationError, match="handler must return None"):

        @watcher.triggers_on(TestModel, "*.jsonl")
        def handler_bool_return(models: List[TestModel], file_path: Path) -> bool:
            return True


def test_helpful_error_messages():
    """Test that error messages are helpful and specific."""
    watcher = WatchdanticCore()

    # Test specific error message for wrong model type
    with pytest.raises(ConfigurationError) as exc_info:

        @watcher.triggers_on(TestModel, "*.jsonl")
        def bad_model_handler(models: TestModel, file_path: Path) -> None:
            pass

    error_msg = str(exc_info.value)
    assert "List[TestModel]" in error_msg
    assert "first parameter" in error_msg
    assert "matching the decorator's model_class" in error_msg

    # Test path error message
    with pytest.raises(ConfigurationError) as exc_info:

        @watcher.triggers_on(TestModel, "*.jsonl")
        def bad_path_handler(models: List[TestModel], file_path: str) -> None:
            pass

    error_msg = str(exc_info.value)
    assert "pathlib.Path" in error_msg
    assert "second parameter" in error_msg

    # Test wrong model class error
    with pytest.raises(ConfigurationError) as exc_info:

        @watcher.triggers_on(TestModel, "*.jsonl")
        def wrong_model_class_handler(models: List[AlternativeModel], file_path: Path) -> None:
            pass

    error_msg = str(exc_info.value)
    assert "TestModel" in error_msg
    assert "AlternativeModel" in error_msg or "List[TestModel]" in error_msg


def test_parameter_count_validation():
    """Test validation of parameter count."""
    watcher = WatchdanticCore()

    # Too few parameters
    with pytest.raises(ConfigurationError, match="handler must accept exactly two parameters"):

        @watcher.triggers_on(TestModel, "*.jsonl")
        def too_few_params(models: List[TestModel]) -> None:
            pass

    # Too many parameters
    with pytest.raises(ConfigurationError, match="handler must accept exactly two parameters"):

        @watcher.triggers_on(TestModel, "*.jsonl")
        def too_many_params(models: List[TestModel], file_path: Path, extra: str) -> None:
            pass

    # No parameters
    with pytest.raises(ConfigurationError, match="handler must accept exactly two parameters"):

        @watcher.triggers_on(TestModel, "*.jsonl")
        def no_params() -> None:
            pass


def test_list_vs_list_annotations():
    """Test that both typing.List and builtin list work correctly."""
    watcher = WatchdanticCore()

    # Clear any existing handlers
    watcher.registry.clear()

    # Test typing.List
    @watcher.triggers_on(TestModel, "*.jsonl")
    def typing_list_handler(models: List[TestModel], file_path: Path) -> None:
        pass

    # Test builtin list (Python 3.9+)
    @watcher.triggers_on(TestModel, "*.json")
    def builtin_list_handler(models: list[TestModel], file_path: Path) -> None:
        pass

    # Both should work
    handlers = watcher.registry.get_handler_names()
    assert "typing_list_handler" in handlers
    assert "builtin_list_handler" in handlers

    # Verify they're properly registered with correct types
    typing_handler = watcher.registry.handlers["typing_list_handler"]
    builtin_handler = watcher.registry.handlers["builtin_list_handler"]

    assert typing_handler.model_class == TestModel
    assert builtin_handler.model_class == TestModel


def test_complex_generic_types():
    """Test handling of more complex generic type scenarios."""
    watcher = WatchdanticCore()

    # Test with nested generic (should fail - not List[Model])
    with pytest.raises(ConfigurationError):

        @watcher.triggers_on(TestModel, "*.jsonl")
        def nested_generic_handler(models: List[List[TestModel]], file_path: Path) -> None:
            pass

    # Test with Optional (should fail - not List[Model])
    from typing import Optional

    with pytest.raises(ConfigurationError):

        @watcher.triggers_on(TestModel, "*.jsonl")
        def optional_handler(models: Optional[List[TestModel]], file_path: Path) -> None:
            pass


def test_string_annotations():
    """Test handling of string type annotations (forward references)."""
    watcher = WatchdanticCore()

    # This should work with string annotations
    @watcher.triggers_on(TestModel, "*.jsonl")
    def string_annotation_handler(models: "List[TestModel]", file_path: "Path") -> None:
        pass

    # Verify it was registered
    assert "string_annotation_handler" in watcher.registry.get_handler_names()

    # Test wrong string annotation
    with pytest.raises(ConfigurationError):

        @watcher.triggers_on(TestModel, "*.jsonl")
        def wrong_string_annotation(models: "List[AlternativeModel]", file_path: Path) -> None:
            pass


def test_edge_cases():
    """Test edge cases and boundary conditions."""
    watcher = WatchdanticCore()

    # Handler with very long name should work
    very_long_name = "a" * 100

    def make_handler():
        def handler_func(models: List[TestModel], file_path: Path) -> None:
            pass

        handler_func.__name__ = very_long_name
        return handler_func

    handler = make_handler()
    decorated = watcher.triggers_on(TestModel, "*.jsonl")(handler)
    assert very_long_name in watcher.registry.get_handler_names()

    # Test with different model classes
    class CustomModel(BaseModel):
        data: str

    @watcher.triggers_on(CustomModel, "*.jsonl")
    def custom_model_handler(models: List[CustomModel], file_path: Path) -> None:
        pass

    custom_handler_info = watcher.registry.handlers["custom_model_handler"]
    assert custom_handler_info.model_class == CustomModel
