import jsonschema
import pytest

from docent.judges.types import Rubric
from docent.judges.util.meta_schema import validate_judge_result_schema


def _valid_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "label": {"type": "string"},
            "score": {"type": "number"},
        },
        "required": ["label"],
        "additionalProperties": False,
    }


def test_validate_judge_result_schema_accepts_valid_schema():
    validate_judge_result_schema(_valid_schema())


def test_validate_judge_result_schema_missing_properties_raises_validation_error():
    with pytest.raises(jsonschema.ValidationError, match="'properties' is a required property"):
        validate_judge_result_schema({"type": "object"})


def test_validate_judge_result_schema_unknown_type_raises_schema_error():
    schema = {
        "type": "object",
        "properties": {"label": {"type": "invalid"}},
    }

    with pytest.raises(
        jsonschema.SchemaError, match="'invalid' is not valid under any of the given schemas"
    ):
        validate_judge_result_schema(schema)


def test_rubric_accepts_valid_output_schema():
    rubric = Rubric(rubric_text="Example rubric", output_schema=_valid_schema())
    assert rubric.output_schema["required"] == ["label"]


def test_rubric_invalid_schema_missing_properties_propagates_validation_error():
    with pytest.raises(jsonschema.ValidationError, match="'properties' is a required property"):
        Rubric(rubric_text="Example rubric", output_schema={"type": "object"})


def test_rubric_invalid_schema_unknown_type_propagates_schema_error():
    schema = {
        "type": "object",
        "properties": {"label": {"type": "madeup"}},
    }

    with pytest.raises(
        jsonschema.SchemaError, match="'madeup' is not valid under any of the given schemas"
    ):
        Rubric(rubric_text="Example rubric", output_schema=schema)
