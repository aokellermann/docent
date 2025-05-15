from __future__ import annotations

from typing import Any, Protocol, cast
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from docent._frames.transcript import (
    Citation,
    Transcript,
    TranscriptMetadata,
    parse_citations_single_transcript,
)

SINGLETONS = (int, float, str, bool)


class Datapoint(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str | None = None
    attributes: dict[str, list[str]] = Field(default_factory=dict)
    obj: Transcript

    @property
    def metadata(self) -> TranscriptMetadata:
        return self.obj.metadata

    @property
    def text(self) -> str:
        return self.obj.to_str()

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return super().model_dump(*args, **kwargs) | {"text": self.text}

    @classmethod
    def from_transcript(cls, transcript: Transcript, id_prefix: str | None = None) -> Datapoint:
        return cls(
            obj=transcript,
            name=f"{id_prefix}_{transcript.metadata.task_id}_{transcript.metadata.sample_id}_{transcript.metadata.experiment_id}_{transcript.metadata.epoch_id}".replace(
                "/", "_"
            ),
        )


class TranscriptMetadataBase(BaseModel):
    @model_validator(mode="after")
    def validate_field_types_and_descriptions(self):
        """Validate that all fields have descriptions and proper types."""

        # Validate each field in the model
        for field_name, field_info in TranscriptMetadataBase.model_fields.items():
            # Check that each field has a description
            if field_info.description is None:
                raise ValueError(f"Field '{field_name}' must have a description")

            # Validate field types
            field_value = getattr(self, field_name, None)
            if field_value is None:
                continue
            self._validate_field_value_type(field_name, field_value)

        return self

    def _validate_field_value_type(self, field_name: str, value: Any) -> None:
        """Validate that a field value is of the allowed types."""
        # Skip None values
        if value is None:
            return

        # Check for singleton types
        if isinstance(value, SINGLETONS):
            return

        # Check for list of singletons
        if isinstance(value, list):
            for item in cast(list[Any], value):
                if not isinstance(item, SINGLETONS):
                    raise ValueError(
                        f"Field '{field_name}' contains a list with non-singleton values. "
                        f"All list items must be one of {SINGLETONS}"
                    )
            return

        # Check for dict from str to singletons
        if isinstance(value, dict):
            value = cast(dict[str, Any], value)
            for k in value.keys():
                if not isinstance(k, str):
                    raise ValueError(
                        f"Field '{field_name}' contains a dict with non-string keys. "
                        f"All dict keys must be strings."
                    )

            for v in value.values():
                if not (
                    isinstance(v, SINGLETONS)
                    or (
                        isinstance(v, list)
                        and all(isinstance(i, SINGLETONS) for i in cast(list[Any], v))
                    )
                    or (
                        isinstance(v, dict)
                        and all(isinstance(k, str) for k in cast(dict[Any, Any], v).keys())
                    )
                ):
                    raise ValueError(
                        f"Field '{field_name}' contains a dict with invalid values. "
                        f"All dict values must be singletons, lists of singletons, or dicts with string keys."
                    )
            return

        # If we get here, the field type is invalid
        raise ValueError(
            f"Field '{field_name}' has an invalid type. Must be a singleton "
            f"({SINGLETONS}), a list of singletons, or a dict from str to singletons."
        )


class Judgment(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    datapoint_id: str
    attribute: str | None = None
    attribute_idx: int | None = None

    matches: bool
    reason: str | None = None


class Attribute(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    datapoint_id: str
    attribute: str
    attribute_idx: int | None = None
    value: str | None = None


class AttributeWithCitations(Attribute):
    citations: list[Citation] | None

    @classmethod
    def from_attribute(cls, attribute: Attribute) -> AttributeWithCitations:
        return cls(
            **attribute.model_dump(),
            citations=(
                parse_citations_single_transcript(attribute.value)
                if attribute.value is not None
                else None
            ),
        )


class AssignmentStreamingCallback(Protocol):
    async def __call__(
        self,
        batch_index: int,
        assignment: tuple[bool, str] | None,
    ) -> None: ...


class JudgmentStreamingCallback(Protocol):
    async def __call__(
        self,
        data_index: int,
        attribute_index: int,
        judgment: Judgment,
    ) -> None: ...


class RegexSnippet(BaseModel):
    snippet: str
    match_start: int
    match_end: int
