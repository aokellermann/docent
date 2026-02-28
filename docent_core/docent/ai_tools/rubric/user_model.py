"""Data structures for run-centric feedback elicitation user data and user models."""

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

    question: str
    question_citations: list[InlineCitation] = Field(default_factory=list[InlineCitation])
    sample_answers: list[str] = Field(default_factory=list[str])
    selected_sample_index: int | None = None
    answer: str
    explanation: str | None = None
    status: Literal["answered", "skipped"]
    is_custom_response: bool = False
    timestamp: datetime = Field(default_factory=datetime.now)


class LabelingRequest(BaseModel):
    """Structured labeling request shown to the user."""

    agent_run_id: str
    title: str
    priority_rationale: str
    priority_rationale_citations: list[InlineCitation] = Field(default_factory=list[InlineCitation])
    review_context: str
    review_context_citations: list[InlineCitation] = Field(default_factory=list[InlineCitation])
    review_focus: list[LabelingRequestFocusItem] = Field(
        default_factory=list[LabelingRequestFocusItem]
    )


class LabeledRun(BaseModel):
    """A human label for one agent run."""

    agent_run_id: str
    label_value: dict[str, Any]  # Matches Label.label_value pattern
    explanation: str | None = None
    labeling_request: LabelingRequest | None = None
    metadata: dict[str, Any] | None = None
    timestamp: datetime = Field(default_factory=datetime.now)


class AgentRunFeedback(BaseModel):
    """All feedback collected for a single agent run."""

    agent_run_id: str
    title: str
    review_context: str
    review_context_citations: list[InlineCitation] = Field(default_factory=list[InlineCitation])
    priority_rationale: str
    priority_rationale_citations: list[InlineCitation] = Field(default_factory=list[InlineCitation])
    qa_pairs: list[QAPair] = Field(default_factory=list[QAPair])
    label: LabeledRun | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    last_updated: datetime = Field(default_factory=datetime.now)


class UserData(BaseModel):
    """User Data (U) for user-model inference and downstream evaluation."""

    initial_rubric: str
    agent_run_feedback: list[AgentRunFeedback] = Field(
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
        normalized_feedback.last_updated = now

        for idx, existing in enumerate(self.agent_run_feedback):
            if existing.agent_run_id != normalized_feedback.agent_run_id:
                continue
            normalized_feedback.created_at = existing.created_at
            self.agent_run_feedback[idx] = normalized_feedback
            self.last_updated = now
            return

        self.agent_run_feedback.append(normalized_feedback)
        self.last_updated = now

    def iter_answered_qa_entries(self) -> Iterator[tuple[AgentRunFeedback, QAPair]]:
        """Iterate answered QA pairs with their parent run feedback."""
        for feedback in self.agent_run_feedback:
            for qa_pair in feedback.qa_pairs:
                if qa_pair.status == "answered":
                    yield feedback, qa_pair

    def iter_skipped_qa_entries(self) -> Iterator[tuple[AgentRunFeedback, QAPair]]:
        """Iterate skipped QA pairs with their parent run feedback."""
        for feedback in self.agent_run_feedback:
            for qa_pair in feedback.qa_pairs:
                if qa_pair.status == "skipped":
                    yield feedback, qa_pair

    def iter_labeled_entries(self) -> Iterator[tuple[AgentRunFeedback, LabeledRun]]:
        """Iterate labeled run entries with their parent run feedback."""
        for feedback in self.agent_run_feedback:
            if feedback.label is None:
                continue
            yield feedback, feedback.label


class UserModel(BaseModel):
    """User Model (z) - Markdown representation of user intent"""

    model_text: str
    version: int = 1
    user_data: UserData
    created_at: datetime = Field(default_factory=datetime.now)
    last_updated: datetime = Field(default_factory=datetime.now)

    def update_model(self, new_model_text: str) -> None:
        """Update the model text and increment version."""
        self.model_text = new_model_text
        self.version += 1
        self.last_updated = datetime.now()
