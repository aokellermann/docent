from __future__ import annotations

import pytest

from docent._llm_util.llm_svc import BaseLLMService
from docent.data_models.citation import AgentRunMetadataItem, CitationTarget, InlineCitation
from docent_core.docent.ai_tools.rubric import elicit
from docent_core.docent.ai_tools.rubric.user_model import (
    AgentRunFeedback,
    LabeledRun,
    QAPair,
    UserData,
)


class _UnusedLLMService(BaseLLMService):
    async def get_completions(self, *args, **kwargs):  # type: ignore[override]
        raise AssertionError("LLM should not be called for fallback inference")


def _dummy_citation() -> InlineCitation:
    return InlineCitation(
        start_idx=0,
        end_idx=1,
        target=CitationTarget(
            item=AgentRunMetadataItem(
                agent_run_id="run-1",
                collection_id="collection-1",
                metadata_key="key",
            )
        ),
    )


def test_parse_labeling_request_payload_normalizes_focus_and_priority_citations(
    monkeypatch: pytest.MonkeyPatch,
):
    citation = _dummy_citation()

    def _resolve(text: str, _context: object, validate_text_ranges: bool = True):
        del validate_text_ranges
        return text.replace("[cite]", "").strip(), [citation]

    monkeypatch.setattr(elicit, "resolve_citations_with_context", _resolve)

    parsed_payload = {
        "title": "Review this run",
        "priority_rationale": "High uncertainty [cite]",
        "review_context": "The run has mixed evidence [cite]",
        "review_focus": [
            {
                "question": "Is the conclusion justified? [cite]",
                "sample_answers": [" yes ", "no", "yes", "", 123, "maybe", "extra"],
            },
            {
                "question": "Was uncertainty acknowledged?",
                "sample_answers": ["partially"],
            },
            {"question": 123, "sample_answers": ["ignored"]},
            "ignored",
        ],
    }

    request = elicit.parse_labeling_request_payload(
        parsed=parsed_payload,
        agent_run_id="run-1",
        context=object(),  # type: ignore[arg-type]
    )

    assert request.title == "Review this run"
    assert request.priority_rationale == "High uncertainty"
    assert request.priority_rationale_citations == [citation]
    assert request.review_context_citations == [citation]

    assert len(request.review_focus) == 2
    assert request.review_focus[0].question == "Is the conclusion justified?"
    assert request.review_focus[0].sample_answers == ["yes", "no", "maybe"]
    assert request.review_focus[0].citations == [citation]
    assert request.review_focus[1].sample_answers == ["partially"]


def test_summarize_user_data_for_prompt_uses_answered_qa_and_labels_only():
    user_data = UserData(
        initial_rubric="rubric",
        agent_run_feedback=[
            AgentRunFeedback(
                agent_run_id="run-1",
                title="Run 1",
                review_context="Context 1",
                review_context_citations=[],
                priority_rationale="Priority 1",
                priority_rationale_citations=[],
                qa_pairs=[
                    QAPair(
                        question="Answered question",
                        question_citations=[],
                        sample_answers=["a", "b"],
                        selected_sample_index=0,
                        answer="Answered text",
                        status="answered",
                        is_custom_response=False,
                    ),
                    QAPair(
                        question="Skipped question",
                        question_citations=[],
                        sample_answers=["x", "y"],
                        selected_sample_index=None,
                        answer="",
                        status="skipped",
                        is_custom_response=False,
                    ),
                ],
                label=LabeledRun(agent_run_id="run-1", label_value={"pass": True}),
            ),
            AgentRunFeedback(
                agent_run_id="run-2",
                title="Run 2",
                review_context="Context 2",
                review_context_citations=[],
                priority_rationale="Priority 2",
                priority_rationale_citations=[],
                qa_pairs=[
                    QAPair(
                        question="Only skipped",
                        question_citations=[],
                        sample_answers=["n/a"],
                        selected_sample_index=None,
                        answer="",
                        status="skipped",
                        is_custom_response=False,
                    )
                ],
                label=None,
            ),
        ],
    )

    summary = elicit.summarize_user_data_for_prompt(user_data=user_data, max_tokens=10_000)

    assert "Answered question" in summary
    assert "Skipped question" not in summary
    assert '"pass": true' in summary.lower()


@pytest.mark.asyncio
async def test_infer_user_model_falls_back_when_no_answered_or_labeled_feedback():
    user_data = UserData(
        initial_rubric="fallback rubric",
        agent_run_feedback=[
            AgentRunFeedback(
                agent_run_id="run-1",
                title="Run 1",
                review_context="Context",
                review_context_citations=[],
                priority_rationale="Priority",
                priority_rationale_citations=[],
                qa_pairs=[
                    QAPair(
                        question="Skipped question",
                        question_citations=[],
                        sample_answers=["a"],
                        selected_sample_index=None,
                        answer="",
                        status="skipped",
                        is_custom_response=False,
                    )
                ],
                label=None,
            )
        ],
    )

    model_text = await elicit.infer_user_model_from_user_data(
        user_data=user_data,
        llm_svc=_UnusedLLMService(),
    )

    assert model_text == "fallback rubric"
