from typing import Any

import yaml
from pydantic_core import to_jsonable_python


def yaml_dump_metadata(metadata: dict[str, Any]) -> str | None:
    if not metadata:
        return None
    metadata_obj = to_jsonable_python(metadata)
    yaml_text = yaml.dump(metadata_obj, width=float("inf"))
    return yaml_text.strip()
