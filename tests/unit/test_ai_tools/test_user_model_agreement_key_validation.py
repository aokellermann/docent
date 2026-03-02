import pytest

from docent.judges.util.voting import DistributionOutcome, OutputDistribution
from docent_core.docent.ai_tools.rubric.user_model import (
    AgentRunFeedback,
    LabeledRun,
    LabelingRequest,
    UserData,
)


def _build_feedback(
    run_id: str,
    *,
    label_value: dict[str, object] | None = None,
    distribution_output: dict[str, object] | None = None,
) -> AgentRunFeedback:
    user_distribution = (
        OutputDistribution(
            outcomes=[DistributionOutcome(output=distribution_output, probability=1.0)]
        )
        if distribution_output is not None
        else None
    )
    labeling_request = LabelingRequest(
        agent_run_id=run_id,
        title="Label this run",
        review_context="ctx",
        review_context_citations=[],
        review_focus=[],
        user_distribution=user_distribution,
        user_distribution_reasoning=None,
    )
    label = (
        LabeledRun(agent_run_id=run_id, label_value=label_value, explanation=None)
        if label_value is not None
        else None
    )
    return AgentRunFeedback(
        agent_run_id=run_id,
        labeling_request=labeling_request,
        qa_pairs=[],
        label=label,
    )


def test_validate_against_agreement_keys_accepts_valid_user_data():
    user_data = UserData(
        initial_rubric="rubric",
        agent_run_feedbacks=[
            _build_feedback(
                "run-1",
                label_value={"label": "match"},
                distribution_output={"label": "match", "flag": True},
            )
        ],
    )

    user_data.validate_against_agreement_keys({"label", "flag"})


def test_validate_against_agreement_keys_rejects_invalid_label_keys():
    user_data = UserData(
        initial_rubric="rubric",
        agent_run_feedbacks=[
            _build_feedback("run-1", label_value={"label": "match", "notes": "x"})
        ],
    )

    with pytest.raises(ValueError, match="label_value"):
        user_data.validate_against_agreement_keys({"label"})


def test_validate_against_agreement_keys_rejects_invalid_distribution_keys():
    user_data = UserData(
        initial_rubric="rubric",
        agent_run_feedbacks=[
            _build_feedback("run-1", distribution_output={"label": "match", "notes": "x"})
        ],
    )

    with pytest.raises(ValueError, match="user_distribution outcome"):
        user_data.validate_against_agreement_keys({"label"})


def test_validate_against_agreement_keys_rejects_non_scalar_distribution_values():
    user_data = UserData(
        initial_rubric="rubric",
        agent_run_feedbacks=[
            _build_feedback("run-1", distribution_output={"label": {"unexpected": "nested"}})
        ],
    )

    with pytest.raises(ValueError, match="non-scalar"):
        user_data.validate_against_agreement_keys({"label"})
