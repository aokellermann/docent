from collections import Counter
from typing import Any, cast


def get_agreement_keys(schema: dict[str, Any]) -> list[str]:
    """Get list of top-level keys in schema that we want to measure agreement on.

    This includes enum, bool, and int fields. We skip float and strings.

    Args:
        schema: JSON schema dict

    Returns:
        List of field names (keys) that should be used for measuring agreement
    """
    agreement_keys: list[str] = []

    properties = schema.get("properties", {})
    assert isinstance(properties, dict)
    properties = cast(dict[str, Any], properties)

    for key, field_schema in properties.items():
        assert isinstance(field_schema, dict)
        field_schema = cast(dict[str, Any], field_schema)

        field_type = field_schema.get("type")
        assert isinstance(field_type, str)

        # Include boolean fields
        if field_type == "boolean":
            agreement_keys.append(key)
        # Include integer fields
        elif field_type == "integer":
            agreement_keys.append(key)
        # Include enum fields (even strings)
        elif "enum" in field_schema:
            agreement_keys.append(key)

    return agreement_keys


def find_modal_result(indep_results: list[dict[str, Any]], agreement_keys: list[str]):
    """Find the result that best matches modal values across agreement keys.

    Args:
        indep_results: List of independent results to analyze
        agreement_keys: Keys to measure agreement on

    Returns:
        Tuple of (max_idx, agt_key_modes_and_counts) where:
        - max_idx is the index of the result that best matches modal values
        - agt_key_modes_and_counts maps each key to (modal_value, count) or None if no values exist for that key

    Raises:
        ValueError: If no results are provided
    """
    if not indep_results:
        raise ValueError("No results to score")

    # For each agreement key, compute the mode and count (or None, if no values exist for that key)
    agt_key_modes_and_counts: dict[str, tuple[str | bool | int, int] | None] = {}
    for key in agreement_keys:
        key_modes = Counter(v for r in indep_results if (v := r.get(key)) is not None)
        if most_common_one := key_modes.most_common(1):
            agt_key_modes_and_counts[key] = most_common_one[0]
        else:
            agt_key_modes_and_counts[key] = None

    # Score each rollout based on how many agreement keys they match
    # If there is no mode for a key, or if a certain result doesn't have that key, it doesn't count.
    # TODO(mengk): This may bias towards results that have more keys.
    indep_result_scores: list[int] = []
    for r in indep_results:
        score = 0
        for key in agreement_keys:
            mode_and_count = agt_key_modes_and_counts[key]
            if mode_and_count and r.get(key) == mode_and_count[0]:
                score += 1
        indep_result_scores.append(score)

    # Argmax
    max_idx = indep_result_scores.index(max(indep_result_scores))

    return max_idx, agt_key_modes_and_counts
