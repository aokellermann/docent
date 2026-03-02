"""Data structures for run-centric feedback elicitation and user context inference."""

from collections.abc import Iterator
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from docent.data_models.citation import InlineCitation
from docent.judges.util.voting import OutputDistribution


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
    user_distribution: OutputDistribution | None = None
    user_distribution_reasoning: str | None = None


class LabeledRun(BaseModel):
    """A human label for one agent run."""

    agent_run_id: str
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

    @model_validator(mode="after")
    def validate_nested_agent_run_ids(self) -> "AgentRunFeedback":
        """Ensure nested run IDs are consistent with the top-level run ID."""
        if self.labeling_request.agent_run_id != self.agent_run_id:
            raise ValueError("labeling_request.agent_run_id must match agent_run_id")
        if self.label is not None and self.label.agent_run_id != self.agent_run_id:
            raise ValueError("label.agent_run_id must match agent_run_id")
        return self


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
        upserted_feedback = agent_run_feedback.model_copy(deep=True)
        upserted_feedback.last_updated = now

        for idx, existing in enumerate(self.agent_run_feedbacks):
            if existing.agent_run_id != upserted_feedback.agent_run_id:
                continue
            upserted_feedback.created_at = existing.created_at
            self.agent_run_feedbacks[idx] = upserted_feedback
            self.last_updated = now
            return

        self.agent_run_feedbacks.append(upserted_feedback)
        self.last_updated = now

    def validate_against_agreement_keys(self, agreement_keys: set[str]) -> None:
        """Validate stored labels and p_u outcomes against rubric agreement keys."""
        for feedback in self.agent_run_feedbacks:
            run_id = feedback.agent_run_id

            label = feedback.label
            if label is not None:
                invalid_label_keys = sorted(set(label.label_value.keys()) - agreement_keys)
                if invalid_label_keys:
                    raise ValueError(
                        "Run "
                        f"{run_id} has label_value keys outside rubric agreement keys: "
                        + ", ".join(invalid_label_keys)
                    )

            user_distribution = feedback.labeling_request.user_distribution
            if user_distribution is None:
                continue

            for outcome_idx, outcome in enumerate(user_distribution.outcomes, start=1):
                invalid_output_keys = sorted(set(outcome.output.keys()) - agreement_keys)
                if invalid_output_keys:
                    raise ValueError(
                        "Run "
                        f"{run_id} has user_distribution outcome #{outcome_idx} keys outside "
                        "rubric agreement keys: " + ", ".join(invalid_output_keys)
                    )
                for key, value in outcome.output.items():
                    if isinstance(value, (str, bool, int, float)):
                        continue
                    raise ValueError(
                        "Run "
                        f"{run_id} has user_distribution outcome #{outcome_idx} non-scalar "
                        f"value for key '{key}': {type(value).__name__}"
                    )

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
