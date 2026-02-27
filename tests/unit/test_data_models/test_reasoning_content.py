import pytest

from docent.data_models.chat import AssistantMessage, parse_chat_message
from docent.data_models.chat.content import ContentReasoning, ContentText
from docent.data_models.transcript import format_chat_message


@pytest.mark.unit
def test_parse_chat_message_preserves_redacted_reasoning_summary():
    message = parse_chat_message(
        {
            "role": "assistant",
            "content": [
                {
                    "type": "reasoning",
                    "reasoning": "a1b2-c3d4-encrypted",
                    "summary": "Short summary for users",
                    "redacted": True,
                    "signature": "sig_123",
                },
                {"type": "text", "text": "Final answer"},
            ],
        }
    )

    assert isinstance(message, AssistantMessage)
    assert isinstance(message.content, list)

    reasoning_item = message.content[0]
    assert isinstance(reasoning_item, ContentReasoning)
    assert reasoning_item.reasoning == "a1b2-c3d4-encrypted"
    assert reasoning_item.summary == "Short summary for users"
    assert reasoning_item.redacted is True
    assert reasoning_item.signature == "sig_123"


@pytest.mark.unit
def test_format_chat_message_uses_summary_for_redacted_reasoning():
    message = AssistantMessage(
        content=[
            ContentReasoning(
                reasoning="a1b2-c3d4-encrypted",
                summary="Human-readable reasoning",
                redacted=True,
            ),
            ContentText(text="Final answer"),
        ]
    )

    formatted = format_chat_message(message=message, index_label="T0B0")

    assert "Human-readable reasoning" in formatted
    assert "a1b2-c3d4-encrypted" not in formatted


@pytest.mark.unit
def test_format_chat_message_keeps_reasoning_when_not_redacted():
    message = AssistantMessage(
        content=[
            ContentReasoning(
                reasoning="Plain reasoning",
                summary="This should not replace reasoning",
                redacted=False,
            ),
            ContentText(text="Final answer"),
        ]
    )

    formatted = format_chat_message(message=message, index_label="T0B0")

    assert "Plain reasoning" in formatted
    assert "This should not replace reasoning" not in formatted


@pytest.mark.unit
def test_format_chat_message_falls_back_when_redacted_summary_missing():
    message = AssistantMessage(
        content=[
            ContentReasoning(
                reasoning="Fallback reasoning",
                summary=None,
                redacted=True,
            ),
            ContentText(text="Final answer"),
        ]
    )

    formatted = format_chat_message(message=message, index_label="T0B0")

    assert "Fallback reasoning" in formatted
