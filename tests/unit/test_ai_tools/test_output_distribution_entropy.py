import math

import pytest

from docent.judges.util.voting import (
    DistributionOutcome,
    OutputDistribution,
    assert_agreement_only_output_schema,
    compute_entropy,
    get_agreement_key_options,
    normalize_output_distribution,
)


def test_normalize_output_distribution_merges_duplicate_outputs():
    distribution = OutputDistribution(
        outcomes=[
            DistributionOutcome(output={"label": "yes", "score": 1}, probability=0.2),
            DistributionOutcome(output={"score": 1, "label": "yes"}, probability=0.5),
            DistributionOutcome(output={"label": "no", "score": 0}, probability=0.3),
        ]
    )

    normalized = normalize_output_distribution(distribution)

    assert len(normalized.outcomes) == 2
    assert normalized.outcomes[0].output == {"label": "yes", "score": 1}
    assert math.isclose(normalized.outcomes[0].probability, 0.7)
    assert normalized.outcomes[1].output == {"label": "no", "score": 0}
    assert math.isclose(normalized.outcomes[1].probability, 0.3)


def test_normalize_output_distribution_uses_uniform_when_mass_is_nonpositive():
    distribution = OutputDistribution(
        outcomes=[
            DistributionOutcome(output={"label": "yes"}, probability=-2.0),
            DistributionOutcome(output={"label": "no"}, probability=0.0),
        ]
    )

    normalized = normalize_output_distribution(distribution)

    assert len(normalized.outcomes) == 2
    assert math.isclose(normalized.outcomes[0].probability, 0.5)
    assert math.isclose(normalized.outcomes[1].probability, 0.5)


def test_compute_entropy_handles_expected_edge_cases():
    distribution = OutputDistribution(
        outcomes=[
            DistributionOutcome(output={"label": "yes", "reason": "r1"}, probability=0.2),
            DistributionOutcome(output={"label": "yes", "reason": "r2"}, probability=0.3),
            DistributionOutcome(output={"label": "no", "reason": "r3"}, probability=0.5),
        ]
    )
    deterministic = OutputDistribution(
        outcomes=[
            DistributionOutcome(output={"label": "yes", "reason": "r1"}, probability=1.0),
            DistributionOutcome(output={"label": "yes", "reason": "r2"}, probability=0.0),
        ]
    )

    expected_entropy = -(0.2 * math.log(0.2) + 0.3 * math.log(0.3) + 0.5 * math.log(0.5))

    assert compute_entropy(OutputDistribution()) == 0.0
    assert compute_entropy(deterministic) == 0.0
    assert math.isclose(compute_entropy(distribution), expected_entropy)


def test_get_agreement_key_options_extracts_enum_and_boolean_values():
    schema = {
        "type": "object",
        "properties": {
            "label": {"type": "string", "enum": ["match", "no_match"]},
            "flag": {"type": "boolean"},
            "notes": {"type": "string"},
        },
    }

    options = get_agreement_key_options(schema)
    assert options == {
        "label": ["match", "no_match"],
        "flag": [True, False],
    }


def test_assert_agreement_only_output_schema_accepts_valid_schema():
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "label": {"type": "string", "enum": ["match", "no_match"]},
            "flag": {"type": "boolean"},
        },
    }

    assert assert_agreement_only_output_schema(schema) == ["label", "flag"]


def test_assert_agreement_only_output_schema_rejects_non_agreement_keys():
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "label": {"type": "string", "enum": ["match", "no_match"]},
            "notes": {"type": "string"},
        },
    }

    with pytest.raises(ValueError, match="non-agreement"):
        assert_agreement_only_output_schema(schema)


def test_assert_agreement_only_output_schema_requires_additional_properties_false():
    schema = {
        "type": "object",
        "properties": {
            "label": {"type": "string", "enum": ["match", "no_match"]},
        },
    }

    with pytest.raises(ValueError, match="additionalProperties"):
        assert_agreement_only_output_schema(schema)


def test_assert_agreement_only_output_schema_requires_at_least_one_key():
    schema: dict[str, object] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {},
    }

    with pytest.raises(ValueError, match="at least one"):
        assert_agreement_only_output_schema(schema)
