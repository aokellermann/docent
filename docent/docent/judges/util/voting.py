import json
import math
from collections import Counter
from typing import Any, TypedDict, cast

import numpy as np
from pydantic import BaseModel, Field

AgreementValue = str | bool | int | float


class EstimateWithCI(TypedDict):
    mean: float
    var: float
    n: int
    ci_95: float


JudgeOutputDistribution = dict[AgreementValue, EstimateWithCI]


class DistributionOutcome(BaseModel):
    """Single outcome and probability mass for a predictive distribution."""

    output: dict[str, Any]
    probability: float


class OutputDistribution(BaseModel):
    """Probability distribution over rubric-compliant outputs."""

    outcomes: list[DistributionOutcome] = Field(default_factory=list[DistributionOutcome])


def _stable_json_dict(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def normalize_output_distribution(distribution: OutputDistribution) -> OutputDistribution:
    """Normalize probabilities and merge duplicate outcomes by canonical JSON output."""
    if not distribution.outcomes:
        return OutputDistribution()

    merged: dict[str, DistributionOutcome] = {}
    for outcome in distribution.outcomes:
        key = _stable_json_dict(outcome.output)
        existing = merged.get(key)
        if existing is None:
            merged[key] = DistributionOutcome(
                output=outcome.output,
                probability=max(0.0, outcome.probability),
            )
            continue

        existing.probability += max(0.0, outcome.probability)

    merged_outcomes = list(merged.values())
    if not merged_outcomes:
        return OutputDistribution()

    total_probability = sum(item.probability for item in merged_outcomes)
    if total_probability <= 0:
        uniform_prob = 1.0 / len(merged_outcomes)
        for item in merged_outcomes:
            item.probability = uniform_prob
    else:
        for item in merged_outcomes:
            item.probability = item.probability / total_probability

    merged_outcomes.sort(key=lambda item: item.probability, reverse=True)

    return OutputDistribution(outcomes=merged_outcomes)


def assert_agreement_only_output_schema(schema: dict[str, Any]) -> list[str]:
    """Validate agreement-only schema contract for elicitation and entropy workflows.

    Contract:
    - Every top-level property must be an agreement key (enum or boolean),
    - ``additionalProperties`` must be explicitly ``False``, and
    - At least one agreement key must exist.
    """
    # if schema.get("additionalProperties") is not False:
    #     raise ValueError(
    #         "Rubric output_schema must set additionalProperties to false for "
    #         "agreement-only entropy workflows."
    #     )

    properties_obj = schema.get("properties")
    if not isinstance(properties_obj, dict):
        raise ValueError("Rubric output_schema must define an object-valued properties field.")
    properties = cast(dict[str, Any], properties_obj)

    agreement_keys = get_agreement_keys(schema)
    if not agreement_keys:
        raise ValueError(
            "Rubric output_schema must include at least one top-level agreement key "
            "(enum or boolean)."
        )

    non_agreement_keys = sorted(set(properties.keys()) - set(agreement_keys))
    if non_agreement_keys:
        details: list[str] = []
        for key in non_agreement_keys:
            field_obj = properties.get(key, {})
            if isinstance(field_obj, dict):
                field_schema = cast(dict[str, Any], field_obj)
                field_type = field_schema.get("type")
                field_type_text = field_type if isinstance(field_type, str) else "unknown"
                has_enum = "enum" in field_schema
                details.append(f"{key} (type={field_type_text}, enum={has_enum})")
            else:
                details.append(f"{key} (type=invalid-schema)")
        raise ValueError(
            "Rubric output_schema includes non-agreement top-level keys: " + ", ".join(details)
        )

    return agreement_keys


def get_agreement_keys(schema: dict[str, Any]) -> list[str]:
    """Get top-level schema keys that support agreement computations.

    This includes top-level enum and boolean fields.
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

        if field_type == "boolean":
            agreement_keys.append(key)
        elif "enum" in field_schema:
            agreement_keys.append(key)

    return agreement_keys


def get_agreement_key_options(
    schema: dict[str, Any],
    agreement_keys: list[str] | None = None,
) -> dict[str, list[AgreementValue]]:
    """Return possible output options for each agreement key from schema."""
    if agreement_keys is None:
        agreement_keys = get_agreement_keys(schema)

    properties = schema.get("properties", {})
    assert isinstance(properties, dict)
    properties = cast(dict[str, Any], properties)

    key_options: dict[str, list[AgreementValue]] = {}
    for key in agreement_keys:
        field_schema_obj = properties.get(key, {})
        assert isinstance(field_schema_obj, dict)
        field_schema = cast(dict[str, Any], field_schema_obj)

        field_type = field_schema.get("type")
        assert isinstance(field_type, str)

        if field_type == "boolean":
            key_options[key] = [True, False]
            continue

        if "enum" in field_schema:
            enum_values = field_schema.get("enum")
            assert isinstance(enum_values, list)
            options: list[AgreementValue] = []
            for enum_value in cast(list[object], enum_values):
                assert isinstance(enum_value, (str, bool, int, float))
                options.append(enum_value)
            key_options[key] = options
            continue

        key_options[key] = []

    return key_options


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


def compute_output_distributions(
    eq_weighted_outputs: list[dict[str, Any]],
    output_schema: dict[str, Any],
    agreement_keys: list[str],
) -> dict[str, JudgeOutputDistribution]:
    """Estimate per-key output value distributions from equally weighted outputs.

    For each key in ``agreement_keys``, this function:
    1. Enumerates allowed values from the schema (``enum`` or ``boolean``),
    2. Counts observed non-null values in ``eq_weighted_outputs``,
    3. Normalizes counts into empirical probabilities, and
    4. Computes per-value summary statistics:
       - ``mean``: empirical probability ``p``
       - ``var``: Bernoulli variance ``p * (1 - p)``
       - ``n``: number of observed (non-null) values for that key
       - ``ci_95``: normal-approximation 95% CI half-width ``1.96 * sqrt(var / n)``

    Optional fields that are missing in some results are skipped (not counted toward ``n``).
    If no values are observed for a key, all value probabilities are set to ``0.0`` and ``n=0``.

    Args:
        eq_weighted_outputs: Output objects to aggregate, each counted with equal weight.
        output_schema: JSON schema used to validate/define allowed output values.
        agreement_keys: Keys to include in the distribution computation.

    Returns:
        Mapping from agreement key to per-value distribution estimates.

    Raises:
        AssertionError: If an observed value is not one of the schema-derived possible values.
    """

    key_options = get_agreement_key_options(output_schema, agreement_keys)
    raw_counts: dict[str, dict[AgreementValue, int]] = {
        key: {value: 0 for value in key_options.get(key, [])} for key in agreement_keys
    }
    # Collect counts for each possible value
    for result in eq_weighted_outputs:
        for key in agreement_keys:
            if (value := result.get(key)) is not None:  # Could be none if the key is optional
                assert value in raw_counts[key], (
                    "this should never happen; the value must be in possible values, since judge results have been validated against the schema"
                )
                raw_counts[key][value] += 1

    distributions: dict[str, JudgeOutputDistribution] = {}
    for agt_key in agreement_keys:
        distributions[agt_key] = {}

        # First normalize the counts to get probabilities
        counts = raw_counts[agt_key]
        total = sum(counts.values())
        probs = {value: (count / total) if total > 0 else 0.0 for value, count in counts.items()}

        for output_key, value in probs.items():
            mean, estimate_var = value, (value * (1 - value))
            # TODO(mengk): change to the wilson score interval
            ci_95 = float(1.96 * np.sqrt(estimate_var / total)) if total > 0 else 0.0
            estimate: EstimateWithCI = {
                "mean": mean,
                "var": estimate_var,
                "n": total,
                "ci_95": ci_95,
            }
            distributions[agt_key][output_key] = estimate

    return distributions


def compute_entropy(distribution: OutputDistribution) -> float:
    """Compute Shannon entropy over normalized outcomes in nats."""
    normalized = normalize_output_distribution(distribution)
    if not normalized.outcomes:
        return 0.0

    entropy = 0.0
    for outcome in normalized.outcomes:
        probability = outcome.probability
        if probability > 0:
            entropy -= probability * math.log(probability)
    return entropy
