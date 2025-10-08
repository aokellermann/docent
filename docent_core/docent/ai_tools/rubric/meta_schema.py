import json
from pathlib import Path
from typing import Any

import jsonschema


def _load_meta_schema() -> dict[str, Any]:
    """Load the rubric meta-schema from the adjacent JSON file."""
    meta_schema_path = Path(__file__).with_suffix(".json")
    with meta_schema_path.open("r", encoding="utf-8") as f:
        return json.load(f)


_META_VALIDATOR = jsonschema.Draft202012Validator(_load_meta_schema())


def validate_judge_result_schema(schema: dict[str, Any]):
    """Validate a proposed schema against the rubric meta-schema.

    Raises:
        jsonschema.ValidationError: If the schema is invalid
        jsonschema.SchemaError: If the schema is not a valid 2020-12 schema
    """
    # First check that this is a valid 2020-12 schema
    jsonschema.Draft202012Validator.check_schema(schema)

    # Then check that it conforms to our subset of the 2020-12 schema
    _META_VALIDATOR.validate(schema)  # type: ignore
