from typing import Annotated, Literal

from pydantic import BaseModel, Discriminator


class BaseContent(BaseModel):
    """Base class for all content types in chat messages.

    Provides the foundation for different content types with a discriminator field.

    Attributes:
        type: The content type identifier, used for discriminating between content types.
    """

    type: Literal["text", "reasoning", "image", "audio", "video"]


class ContentText(BaseContent):
    """Text content for chat messages.

    Represents plain text content in a chat message.

    Attributes:
        type: Fixed as "text" to identify this content type.
        text: The actual text content.
        refusal: Optional flag indicating if this is a refusal message.
    """

    type: Literal["text"] = "text"  # type: ignore
    text: str
    refusal: bool | None = None


class ContentReasoning(BaseContent):
    """Reasoning content for chat messages.

    Represents reasoning or thought process content in a chat message.

    Attributes:
        type: Fixed as "reasoning" to identify this content type.
        reasoning: The actual reasoning text.
        summary: Optional human-readable reasoning summary.
        signature: Optional signature associated with the reasoning.
        redacted: Flag indicating if the reasoning has been redacted.
    """

    type: Literal["reasoning"] = "reasoning"  # type: ignore
    reasoning: str
    summary: str | None = None
    signature: str | None = None
    redacted: bool = False

    @property
    def display_reasoning(self) -> str:
        return self.summary if self.redacted and self.summary else self.reasoning


class ContentImage(BaseContent):
    """Image content for chat messages.

    Attributes:
        type: Fixed as "image" to identify this content type.
        image: The image data (URL or base64-encoded string).
        detail: Level of detail for image processing.
    """

    type: Literal["image"] = "image"  # type: ignore
    image: str
    detail: str | None = None


class ContentAudio(BaseContent):
    """Audio content for chat messages.

    Attributes:
        type: Fixed as "audio" to identify this content type.
        audio: The audio data (URL or base64-encoded string).
    """

    type: Literal["audio"] = "audio"  # type: ignore
    audio: str


class ContentVideo(BaseContent):
    """Video content for chat messages.

    Attributes:
        type: Fixed as "video" to identify this content type.
        video: The video data (URL or base64-encoded string).
    """

    type: Literal["video"] = "video"  # type: ignore
    video: str


# Content type discriminated union
Content = Annotated[
    ContentText | ContentReasoning | ContentImage | ContentAudio | ContentVideo,
    Discriminator("type"),
]
"""Discriminated union of possible content types using the 'type' field."""
