from __future__ import annotations

from typing import Any, cast

from docent_core.docent.ai_tools.rubric.user_model import (
    AgentRunFeedback,
    LabeledRun,
    QAPair,
    UserData,
)
from personal.mengk.rubric_elicit import rubric_bon

rubric_bon_helpers = cast(Any, rubric_bon)


def _feedback_unit(agent_run_id: str, labeled: bool) -> AgentRunFeedback:
    label = LabeledRun(agent_run_id=agent_run_id, label_value={"pass": True}) if labeled else None
    return AgentRunFeedback(
        agent_run_id=agent_run_id,
        title=f"Title {agent_run_id}",
        review_context=f"Context {agent_run_id}",
        review_context_citations=[],
        priority_rationale=f"Priority {agent_run_id}",
        priority_rationale_citations=[],
        qa_pairs=[
            QAPair(
                question="Q",
                question_citations=[],
                sample_answers=["yes", "no"],
                selected_sample_index=0,
                answer="yes",
                status="answered",
                is_custom_response=False,
            )
        ],
        label=label,
    )


def test_split_feedback_units_and_train_context_isolation():
    all_units = [
        _feedback_unit("run-1", labeled=True),
        _feedback_unit("run-2", labeled=False),
        _feedback_unit("run-3", labeled=True),
        _feedback_unit("run-4", labeled=False),
    ]

    train_units, test_units = rubric_bon_helpers._split_feedback_units(
        all_units,
        train_ratio=0.5,
        seed=7,
    )

    assert len(train_units) + len(test_units) == len(all_units)

    train_ids = {unit.agent_run_id for unit in train_units}
    test_ids = {unit.agent_run_id for unit in test_units}
    assert train_ids.isdisjoint(test_ids)

    user_data = UserData(initial_rubric="rubric", agent_run_feedback=all_units)
    train_user_data = rubric_bon_helpers._build_train_user_data(
        user_data=user_data,
        train_feedback_units=train_units,
        initial_rubric="rubric",
    )
    train_context_ids = {unit.agent_run_id for unit in train_user_data.agent_run_feedback}
    assert train_context_ids == train_ids
    assert train_context_ids.isdisjoint(test_ids)

    train_labels = rubric_bon_helpers._extract_labeled_runs(train_units)
    test_labels = rubric_bon_helpers._extract_labeled_runs(test_units)
    assert all(label.agent_run_id in train_ids for label in train_labels)
    assert all(label.agent_run_id in test_ids for label in test_labels)


def test_zero_labeled_split_returns_na_metrics_without_failure():
    evaluation = rubric_bon_helpers._evaluate_split_per_key_accuracy(
        split_name="test",
        judge_results=[],
        labels=[],
        n_rollouts_per_run=3,
    )

    assert evaluation.total_examples == 0
    assert evaluation.overall_key_accuracy is None
    assert evaluation.per_key_accuracy == {}
