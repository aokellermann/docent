from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from docent._llm_util.data_models.llm_output import (
    AsyncLLMOutputStreamingCallback,
    LLMOutput,
)
from docent._llm_util.prod_llms import MessagesInput, get_llm_completions_async
from docent._llm_util.providers.preference_types import ModelOption
from docent.data_models.chat import ToolInfo

__all__ = ["BaseLLMService"]


class BaseLLMService(ABC):
    """Common interface for LLM services."""

    @abstractmethod
    async def get_completions(
        self,
        *,
        inputs: list[MessagesInput],
        model_options: list[ModelOption],
        tools: list[ToolInfo] | None = None,
        tool_choice: Literal["auto", "required"] | None = None,
        max_new_tokens: int = 1024,
        temperature: float = 1.0,
        logprobs: bool = False,
        top_logprobs: int | None = None,
        max_concurrency: int = 100,
        timeout: float = 120.0,
        streaming_callback: AsyncLLMOutputStreamingCallback | None = None,
        validation_callback: AsyncLLMOutputStreamingCallback | None = None,
        completion_callback: AsyncLLMOutputStreamingCallback | None = None,
        use_cache: bool = False,
    ) -> list[LLMOutput]:
        """Request completions from a configured LLM provider."""


class SimpleLLMService(BaseLLMService):
    """Lightweight LLM service that simply forwards completion requests.
    Does not support cost tracking, usage limits, global scheduling or rate limiting."""

    async def get_completions(
        self,
        *,
        inputs: list[MessagesInput],
        model_options: list[ModelOption],
        tools: list[ToolInfo] | None = None,
        tool_choice: Literal["auto", "required"] | None = None,
        max_new_tokens: int = 1024,
        temperature: float = 1.0,
        logprobs: bool = False,
        top_logprobs: int | None = None,
        max_concurrency: int = 100,
        timeout: float = 120.0,
        streaming_callback: AsyncLLMOutputStreamingCallback | None = None,
        validation_callback: AsyncLLMOutputStreamingCallback | None = None,
        completion_callback: AsyncLLMOutputStreamingCallback | None = None,
        use_cache: bool = False,
    ) -> list[LLMOutput]:
        return await get_llm_completions_async(
            inputs=inputs,
            model_options=model_options,
            tools=tools,
            tool_choice=tool_choice,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            logprobs=logprobs,
            top_logprobs=top_logprobs,
            max_concurrency=max_concurrency,
            timeout=timeout,
            streaming_callback=streaming_callback,
            validation_callback=validation_callback,
            completion_callback=completion_callback,
            use_cache=use_cache,
        )
