from __future__ import annotations

from typing import Any, cast

from docent_core.docent.ai_tools.rubric.elicit import OutputDistribution, RunDistributionEstimate
from docent_core.docent.ai_tools.rubric.user_model import LabelingRequest, QAPair, UserData
from personal.mengk.rubric_elicit import label_elicitation

label_elicitation_helpers = cast(Any, label_elicitation)


def _make_labeling_request(agent_run_id: str) -> LabelingRequest:
    return LabelingRequest(
        agent_run_id=agent_run_id,
        title="Title",
        priority_rationale="Priority",
        priority_rationale_citations=[],
        review_context="Context",
        review_context_citations=[],
        review_focus=[],
    )


def _make_estimate(agent_run_id: str) -> RunDistributionEstimate:
    return RunDistributionEstimate(
        agent_run_id=agent_run_id,
        user_distribution=OutputDistribution(outcomes=[]),
    )


def test_build_run_feedback_candidate_supports_qa_only_save_path():
    estimate = _make_estimate("run-1")
    qa_pairs = [
        QAPair(
            question="Question",
            question_citations=[],
            sample_answers=["a", "b"],
            selected_sample_index=0,
            answer="a",
            status="answered",
            is_custom_response=False,
        )
    ]

    feedback = label_elicitation_helpers._build_run_feedback_candidate(
        estimate=estimate,
        entropy=0.25,
        labeling_request=_make_labeling_request("run-1"),
        qa_pairs=qa_pairs,
        label_value={},
        label_explanation=None,
    )

    assert feedback.label is None
    user_data = UserData(initial_rubric="rubric")
    persisted = label_elicitation.persist_run_feedback_with_overwrite_gate(
        user_data=user_data,
        run_feedback=feedback,
        overwrite_confirmed=True,
    )
    assert persisted is True
    assert len(user_data.agent_run_feedback) == 1
    assert user_data.agent_run_feedback[0].label is None


def test_persist_run_feedback_with_overwrite_gate_requires_confirmation_for_replace():
    user_data = UserData(initial_rubric="rubric")

    initial = label_elicitation_helpers._build_run_feedback_candidate(
        estimate=_make_estimate("run-1"),
        entropy=0.1,
        labeling_request=_make_labeling_request("run-1"),
        qa_pairs=[],
        label_value={"pass": False},
        label_explanation="initial",
    )
    replacement = label_elicitation_helpers._build_run_feedback_candidate(
        estimate=_make_estimate("run-1"),
        entropy=0.2,
        labeling_request=_make_labeling_request("run-1"),
        qa_pairs=[],
        label_value={"pass": True},
        label_explanation="replacement",
    )

    assert label_elicitation.persist_run_feedback_with_overwrite_gate(
        user_data=user_data,
        run_feedback=initial,
        overwrite_confirmed=True,
    )

    persisted_without_confirmation = label_elicitation.persist_run_feedback_with_overwrite_gate(
        user_data=user_data,
        run_feedback=replacement,
        overwrite_confirmed=False,
    )
    assert persisted_without_confirmation is False
    assert user_data.agent_run_feedback[0].label is not None
    assert user_data.agent_run_feedback[0].label.label_value == {"pass": False}

    persisted_with_confirmation = label_elicitation.persist_run_feedback_with_overwrite_gate(
        user_data=user_data,
        run_feedback=replacement,
        overwrite_confirmed=True,
    )
    assert persisted_with_confirmation is True
    assert user_data.agent_run_feedback[0].label is not None
    assert user_data.agent_run_feedback[0].label.label_value == {"pass": True}


def test_get_excluded_agent_run_ids_uses_all_existing_feedback_units():
    user_data = UserData(initial_rubric="rubric")
    for run_id in ["run-a", "run-b"]:
        feedback = label_elicitation_helpers._build_run_feedback_candidate(
            estimate=_make_estimate(run_id),
            entropy=0.0,
            labeling_request=_make_labeling_request(run_id),
            qa_pairs=[],
            label_value={},
            label_explanation=None,
        )
        user_data.upsert_run_feedback(feedback)

    excluded_ids = label_elicitation.get_excluded_agent_run_ids(user_data)
    assert excluded_ids == {"run-a", "run-b"}
