import json
from typing import Any, AsyncIterator, Literal, TypedDict

from anthropic import AsyncStream, NotGiven
from anthropic._types import NOT_GIVEN
from anthropic.types import (
    InputJSONDelta,
    RawContentBlockDeltaEvent,
    RawContentBlockStartEvent,
    RawContentBlockStopEvent,
    RawMessageDeltaEvent,
    RawMessageStartEvent,
    RawMessageStreamEvent,
    TextDelta,
    ThinkingDelta,
    ToolParam,
)
from anthropic.types.thinking_config_disabled_param import ThinkingConfigDisabledParam
from anthropic.types.thinking_config_enabled_param import ThinkingConfigEnabledParam
from anthropic.types.thinking_config_param import ThinkingConfigParam

from docent.data_models.chat import AssistantMessage, ChatMessage, ToolCall
from docent.data_models.chat.content import Content, ContentReasoning, ContentText
from docent.data_models.chat.tool import ToolInfo
from docent_core._llm_util.providers.anthropic import (
    parse_chat_messages,
    parse_tools,
)
from docent_core.investigator.tools.backends.anthropic_compatible_backend import (
    ModelWithClient,
)
from docent_core.investigator.tools.common.types import (
    MessageEnd,
    MessageStart,
    TokenDelta,
    ToolCallDelta,
    ToolCallEnd,
    ToolCallStart,
    generate_uid,
)
from docent_core.investigator.tools.subject_models.base import SubjectModelBase


class ToolCallData(TypedDict):
    id: str
    name: str
    arguments: str
    started: bool
    type: Literal["function", "custom"]


class AnthropicCompatibleSubjectModel(SubjectModelBase):
    """Subject model that uses an Anthropic-compatible backend with the Messages API."""

    def __init__(self, model_with_client: ModelWithClient, tools: list[ToolInfo] | None = None):
        self.model_with_client = model_with_client
        self.tools = tools
        self.conversation_history: list[ChatMessage] = []

    async def generate_response_stream(
        self, policy_turn: list[ChatMessage]
    ) -> AsyncIterator[
        TokenDelta | MessageStart | MessageEnd | ToolCallStart | ToolCallDelta | ToolCallEnd
    ]:
        """Generate a streaming response from the Anthropic-compatible model.

        This maintains conversation history and yields a single assistant message
        in response to the policy turn.
        """
        # Add the policy turn to our conversation history
        self.conversation_history.extend(policy_turn)

        # Convert messages to Anthropic format
        system_prompt, anthropic_messages = parse_chat_messages(self.conversation_history)

        # Generate response from the model
        message_id = generate_uid()

        # Yield MessageStart for assistant response
        yield MessageStart(
            message_id=message_id,
            role="assistant",
            is_thinking=False,
        )

        # Prepare tools parameter
        tools_param: list[ToolParam] | NotGiven = (
            parse_tools(self.tools) if self.tools else NOT_GIVEN
        )

        # Prepare thinking parameter
        thinking_param: ThinkingConfigParam | NotGiven = NOT_GIVEN
        if self.model_with_client.thinking:
            if self.model_with_client.thinking.type == "enabled":
                thinking_param = ThinkingConfigEnabledParam(
                    type="enabled",
                    budget_tokens=self.model_with_client.thinking.budget_tokens or 1024,
                )
            elif self.model_with_client.thinking.type == "disabled":
                thinking_param = ThinkingConfigDisabledParam(type="disabled")

        # Stream the response
        stream: AsyncStream[RawMessageStreamEvent] = (
            await self.model_with_client.client.messages.create(
                model=self.model_with_client.model,
                messages=anthropic_messages,
                max_tokens=self.model_with_client.max_tokens,
                system=system_prompt if system_prompt is not None else NOT_GIVEN,
                tools=tools_param,
                thinking=thinking_param,
                stream=True,
            )
        )

        # Collect the full response for history
        full_response = ""
        thinking_content = ""
        tool_calls_data: dict[int, ToolCallData] = {}  # Index -> tool call data

        async for chunk in stream:
            if isinstance(chunk, RawMessageStartEvent):
                # Message is starting - already yielded MessageStart above
                pass
            elif isinstance(chunk, RawContentBlockStartEvent):
                # A new content block is starting
                if chunk.content_block.type == "thinking":
                    # Thinking blocks are part of the same message, just tracked via is_thinking flag
                    pass
                elif chunk.content_block.type == "text":
                    # Regular text blocks - no special handling needed
                    pass
                elif chunk.content_block.type == "tool_use":
                    # Initialize tool call tracking
                    index = chunk.index
                    if index not in tool_calls_data:
                        tool_calls_data[index] = ToolCallData(
                            id=chunk.content_block.id,
                            name=chunk.content_block.name,
                            arguments="",
                            started=False,
                            type="function",
                        )
                    # Emit ToolCallStart
                    yield ToolCallStart(
                        type="function",
                        message_id=message_id,
                        tool_call_id=chunk.content_block.id,
                        function_name=chunk.content_block.name,
                        tool_call_index=index,
                    )
                    tool_calls_data[index]["started"] = True
            elif isinstance(chunk, RawContentBlockDeltaEvent):
                # Content is being streamed
                if isinstance(chunk.delta, TextDelta):
                    # Regular text content
                    yield TokenDelta(
                        message_id=message_id,
                        role="assistant",
                        content=chunk.delta.text,
                        is_thinking=False,
                    )
                    full_response += chunk.delta.text
                elif isinstance(chunk.delta, ThinkingDelta):
                    # Extended thinking content - stream with is_thinking=True
                    yield TokenDelta(
                        message_id=message_id,
                        role="assistant",
                        content=chunk.delta.thinking,
                        is_thinking=True,
                    )
                    thinking_content += chunk.delta.thinking
                elif isinstance(chunk.delta, InputJSONDelta):
                    # Tool call arguments being streamed
                    index = chunk.index
                    if index in tool_calls_data:
                        args_delta = chunk.delta.partial_json
                        tool_calls_data[index]["arguments"] += args_delta
                        if tool_calls_data[index]["started"]:
                            yield ToolCallDelta(
                                type="function",
                                message_id=message_id,
                                tool_call_id=tool_calls_data[index]["id"],
                                arguments_delta=args_delta,
                                tool_call_index=index,
                            )
            elif isinstance(chunk, RawContentBlockStopEvent):
                # Content block has finished - no special handling needed
                pass
            elif isinstance(chunk, RawMessageDeltaEvent):
                # Message-level delta (stop reason, usage)
                pass

        # Emit ToolCallEnd events for all completed tool calls
        for index, tool_data in tool_calls_data.items():
            if tool_data["started"]:
                yield ToolCallEnd(
                    type="function",
                    message_id=message_id,
                    tool_call_id=tool_data["id"],
                    tool_call_index=index,
                )

        # Construct tool calls list for the AssistantMessage
        tool_calls: list[ToolCall] | None = None
        if tool_calls_data:
            tool_calls = []
            for tool_data in tool_calls_data.values():
                if tool_data["id"] and tool_data["name"]:
                    # Parse arguments as JSON
                    parsed_args: dict[str, Any]
                    try:
                        parsed_args = (
                            json.loads(tool_data["arguments"]) if tool_data["arguments"] else {}
                        )
                    except json.JSONDecodeError:
                        # If parsing fails, store as dict with raw key
                        parsed_args = {"raw": tool_data["arguments"]}

                    tool_calls.append(
                        ToolCall(
                            id=tool_data["id"],
                            function=tool_data["name"],
                            arguments=parsed_args,
                            type="function",
                        )
                    )

        # Add the assistant response to conversation history
        # Include thinking blocks to maintain reasoning continuity in multi-turn conversations
        # TODO: support preserving redacted thinking blocks (https://docs.claude.com/en/docs/build-with-claude/extended-thinking#thinking-redaction)
        content: str | list[Content]
        if thinking_content:
            content = []
            if thinking_content:
                content.append(ContentReasoning(reasoning=thinking_content))
            if full_response:
                content.append(ContentText(text=full_response))
        else:
            content = full_response if full_response else ""

        assistant_msg = AssistantMessage(
            content=content,
            role="assistant",
            tool_calls=tool_calls,
        )
        self.conversation_history.append(assistant_msg)

        # Yield MessageEnd
        yield MessageEnd(message_id=message_id)
