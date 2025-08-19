"""
Steps of refinement:
- Search for possible matches
- Generate a list of ambiguities
- Generate a v1 rubric proposal
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from pydantic import BaseModel
from sqlalchemy import DateTime, ForeignKeyConstraint, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from docent.data_models.chat.message import ChatMessage, parse_chat_message
from docent_core._db_service.schemas.base import SQLABase
from docent_core.docent.ai_tools.rubric.rubric import Rubric
from docent_core.docent.db.schemas.rubric import TABLE_RUBRIC

if TYPE_CHECKING:
    from docent_core.docent.db.schemas.rubric import SQLARubric

TABLE_REFINEMENT_AGENT_SESSION = "refinement_agent_sessions"


class RefinementAgentSession(BaseModel):
    id: str
    rubric_id: str
    rubric_version: int
    messages: list[ChatMessage]
    pending_rubric: Rubric | None = None


class SQLARefinementAgentSession(SQLABase):
    __tablename__ = TABLE_REFINEMENT_AGENT_SESSION

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))

    rubric_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    rubric_version: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Composite foreign key constraint
    __table_args__ = (
        ForeignKeyConstraint(
            ["rubric_id", "rubric_version"],
            [f"{TABLE_RUBRIC}.id", f"{TABLE_RUBRIC}.version"],
        ),
    )

    # JSON field to store all messages
    messages: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    pending_rubric: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None), nullable=False, index=True
    )

    # Relationship back to rubric for ORM-level cascading
    rubric: Mapped["SQLARubric"] = relationship(
        "SQLARubric",
        back_populates="refinement_sessions",
    )

    def to_pydantic(self) -> RefinementAgentSession:
        return RefinementAgentSession(
            id=self.id,
            rubric_id=self.rubric_id,
            rubric_version=self.rubric_version,
            messages=[parse_chat_message(m) for m in self.messages],
            pending_rubric=(
                Rubric.model_validate(self.pending_rubric) if self.pending_rubric else None
            ),
        )

    @classmethod
    def from_pydantic(cls, session: RefinementAgentSession) -> "SQLARefinementAgentSession":
        return cls(
            id=session.id,
            rubric_id=session.rubric_id,
            rubric_version=session.rubric_version,
            messages=[m.model_dump() for m in session.messages],
            pending_rubric=session.pending_rubric.model_dump() if session.pending_rubric else None,
        )
