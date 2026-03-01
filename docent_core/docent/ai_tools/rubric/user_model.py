"""Data structures for run-centric feedback elicitation and user context inference."""

from collections.abc import Iterator
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from docent.data_models.citation import InlineCitation


class LabelingRequestFocusItem(BaseModel):
    """Specific rubric-related question the human labeler should inspect."""

    question: str
    citations: list[InlineCitation] = Field(default_factory=list[InlineCitation])
    sample_answers: list[str] = Field(default_factory=list[str])


class QAPair(BaseModel):
    """A single review-focus answer captured for one run."""

    # What the user was shown
    focus_item: LabelingRequestFocusItem

    # Whether the user selected a sample answer or not
    selected_sample_index: int | None = None
    is_custom_response: bool = False

    # What the user responded
    answer: str
    explanation: str | None = None

    # The user could have skipped this question and provided nothing
    status: Literal["answered", "skipped"]
    timestamp: datetime = Field(default_factory=datetime.now)


class LabelingRequest(BaseModel):
    """Structured labeling request shown to the user."""

    agent_run_id: str
    title: str
    review_context: str
    review_context_citations: list[InlineCitation] = Field(default_factory=list[InlineCitation])
    review_focus: list[LabelingRequestFocusItem] = Field(
        default_factory=list[LabelingRequestFocusItem]
    )


class LabeledRun(BaseModel):
    """A human label for one agent run."""

    agent_run_id: str
    metadata: dict[str, Any] | None = None
    timestamp: datetime = Field(default_factory=datetime.now)

    # What the user responded
    label_value: dict[str, Any]
    explanation: str | None = None


class AgentRunFeedback(BaseModel):
    """All feedback collected for a single agent run."""

    agent_run_id: str
    created_at: datetime = Field(default_factory=datetime.now)
    last_updated: datetime = Field(default_factory=datetime.now)

    # What the user was shown
    labeling_request: LabelingRequest

    # What the user responded
    qa_pairs: list[QAPair] = Field(default_factory=list[QAPair])
    label: LabeledRun | None = None


class UserData(BaseModel):
    """User Data (U) for user-context inference and downstream evaluation."""

    initial_rubric: str
    agent_run_feedbacks: list[AgentRunFeedback] = Field(
        default_factory=lambda: list[AgentRunFeedback]()
    )
    created_at: datetime = Field(default_factory=datetime.now)
    last_updated: datetime = Field(default_factory=datetime.now)

    def upsert_run_feedback(self, agent_run_feedback: AgentRunFeedback) -> None:
        """Insert or replace feedback for an agent run ID, updating timestamps."""
        now = datetime.now()
        normalized_feedback = agent_run_feedback.model_copy(deep=True)
        if (
            normalized_feedback.label is not None
            and normalized_feedback.label.agent_run_id != normalized_feedback.agent_run_id
        ):
            normalized_feedback.label = normalized_feedback.label.model_copy(
                update={"agent_run_id": normalized_feedback.agent_run_id}
            )
        if normalized_feedback.labeling_request.agent_run_id != normalized_feedback.agent_run_id:
            normalized_feedback.labeling_request = normalized_feedback.labeling_request.model_copy(
                update={"agent_run_id": normalized_feedback.agent_run_id}
            )
        normalized_feedback.last_updated = now

        for idx, existing in enumerate(self.agent_run_feedbacks):
            if existing.agent_run_id != normalized_feedback.agent_run_id:
                continue
            normalized_feedback.created_at = existing.created_at
            self.agent_run_feedbacks[idx] = normalized_feedback
            self.last_updated = now
            return

        self.agent_run_feedbacks.append(normalized_feedback)
        self.last_updated = now

    def iter_answered_qa_entries(self) -> Iterator[tuple[AgentRunFeedback, QAPair]]:
        """Iterate answered QA pairs with their parent run feedback."""
        for feedback in self.agent_run_feedbacks:
            for qa_pair in feedback.qa_pairs:
                if qa_pair.status == "answered":
                    yield feedback, qa_pair

    def iter_skipped_qa_entries(self) -> Iterator[tuple[AgentRunFeedback, QAPair]]:
        """Iterate skipped QA pairs with their parent run feedback."""
        for feedback in self.agent_run_feedbacks:
            for qa_pair in feedback.qa_pairs:
                if qa_pair.status == "skipped":
                    yield feedback, qa_pair

    def iter_labeled_entries(self) -> Iterator[tuple[AgentRunFeedback, LabeledRun]]:
        """Iterate labeled run entries with their parent run feedback."""
        for feedback in self.agent_run_feedbacks:
            if feedback.label is None:
                continue
            yield feedback, feedback.label
