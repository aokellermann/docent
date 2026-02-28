from __future__ import annotations

from datetime import datetime

from docent_core.docent.ai_tools.rubric.user_model import (
    AgentRunFeedback,
    LabeledRun,
    QAPair,
    UserData,
)


def _make_answered_qa(question: str, answer: str) -> QAPair:
    return QAPair(
        question=question,
        question_citations=[],
        sample_answers=["yes", "no"],
        selected_sample_index=0,
        answer=answer,
        status="answered",
        is_custom_response=False,
    )


def _make_skipped_qa(question: str) -> QAPair:
    return QAPair(
        question=question,
        question_citations=[],
        sample_answers=["yes", "no"],
        selected_sample_index=None,
        answer="",
        status="skipped",
        is_custom_response=False,
    )


def test_user_data_agent_run_feedback_round_trip_and_iterators():
    feedback = AgentRunFeedback(
        agent_run_id="run-1",
        title="Check run",
        review_context="Run context",
        review_context_citations=[],
        priority_rationale="High uncertainty",
        priority_rationale_citations=[],
        qa_pairs=[
            _make_answered_qa("Was the answer grounded?", "Yes, grounded in context."),
            _make_skipped_qa("Was the style concise?"),
        ],
        label=LabeledRun(
            agent_run_id="run-1",
            label_value={"pass": True},
            explanation="Looks good",
        ),
    )
    user_data = UserData(initial_rubric="base rubric", agent_run_feedback=[feedback])

    payload = user_data.model_dump(mode="json")
    hydrated = UserData.model_validate(payload)

    assert len(hydrated.agent_run_feedback) == 1
    assert len(list(hydrated.iter_answered_qa_entries())) == 1
    assert len(list(hydrated.iter_skipped_qa_entries())) == 1
    assert len(list(hydrated.iter_labeled_entries())) == 1


def test_upsert_run_feedback_replaces_existing_by_agent_run_id():
    initial_feedback = AgentRunFeedback(
        agent_run_id="run-1",
        title="Initial",
        review_context="Initial context",
        review_context_citations=[],
        priority_rationale="Initial priority",
        priority_rationale_citations=[],
        qa_pairs=[_make_answered_qa("Q1", "A1")],
        label=LabeledRun(agent_run_id="run-1", label_value={"pass": False}),
        created_at=datetime(2024, 1, 1),
    )
    user_data = UserData(initial_rubric="rubric", agent_run_feedback=[initial_feedback])

    replacement_feedback = AgentRunFeedback(
        agent_run_id="run-1",
        title="Updated",
        review_context="Updated context",
        review_context_citations=[],
        priority_rationale="Updated priority",
        priority_rationale_citations=[],
        qa_pairs=[_make_answered_qa("Q2", "A2")],
        label=LabeledRun(agent_run_id="mismatched-id", label_value={"pass": True}),
    )

    user_data.upsert_run_feedback(replacement_feedback)

    assert len(user_data.agent_run_feedback) == 1
    saved_feedback = user_data.agent_run_feedback[0]
    assert saved_feedback.title == "Updated"
    assert saved_feedback.label is not None
    assert saved_feedback.label.label_value == {"pass": True}
    assert saved_feedback.label.agent_run_id == "run-1"
    assert saved_feedback.created_at == datetime(2024, 1, 1)
