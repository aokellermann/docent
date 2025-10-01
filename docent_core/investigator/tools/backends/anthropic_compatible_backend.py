import os
from typing import TYPE_CHECKING, Any, Literal, Optional

from anthropic import AsyncAnthropic
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from docent_core.investigator.db.schemas.experiment import SQLAAnthropicCompatibleBackend


class ThinkingConfig(BaseModel):
    """Configuration for Claude's extended thinking feature."""

    type: Literal["enabled", "disabled"]
    budget_tokens: Optional[int] = Field(
        default=None,
        ge=1024,
        description="Number of tokens Claude can use for internal reasoning. Must be ≥1024 and less than max_tokens. Required when type='enabled'.",
    )

    def model_post_init(self, __context: Any) -> None:
        """Validate thinking config after initialization."""
        if self.type == "enabled" and self.budget_tokens is None:
            raise ValueError("budget_tokens is required when thinking type is 'enabled'")
        if self.type == "disabled" and self.budget_tokens is not None:
            raise ValueError("budget_tokens should not be set when thinking type is 'disabled'")


class ModelWithClient(BaseModel):
    """
    Instantiated model with an Anthropic client, useful for packaging these together.
    """

    model_config = {"arbitrary_types_allowed": True}

    client: AsyncAnthropic
    model: str
    max_tokens: int
    thinking: Optional[ThinkingConfig]


class AnthropicCompatibleBackendConfig(BaseModel):
    """Anthropic compatible backend configuration."""

    id: str
    name: str
    provider: str
    model: str
    max_tokens: int = Field(
        ge=1, description="Maximum number of tokens to generate before stopping"
    )
    thinking: Optional[ThinkingConfig] = Field(
        default=None, description="Extended thinking configuration"
    )
    api_key: Optional[str] = None
    base_url: Optional[str] = None

    def model_post_init(self, __context: Any) -> None:
        """Validate the config after initialization."""
        # If thinking is enabled, ensure budget_tokens < max_tokens
        if self.thinking and self.thinking.type == "enabled":
            if self.thinking.budget_tokens and self.thinking.budget_tokens >= self.max_tokens:
                raise ValueError(
                    f"thinking.budget_tokens ({self.thinking.budget_tokens}) must be less than max_tokens ({self.max_tokens})"
                )

    @classmethod
    def from_sql(
        cls, backend: "SQLAAnthropicCompatibleBackend"
    ) -> "AnthropicCompatibleBackendConfig":
        """Create config from SQL model."""
        thinking = None
        if backend.thinking_type is not None:
            thinking = ThinkingConfig(
                type=backend.thinking_type, budget_tokens=backend.thinking_budget_tokens
            )

        return cls(
            id=backend.id,
            name=backend.name,
            provider=backend.provider,
            model=backend.model,
            max_tokens=backend.max_tokens,
            thinking=thinking,
            api_key=backend.api_key,
            base_url=backend.base_url,
        )

    def build_client(self) -> ModelWithClient:
        """Build an Anthropic client based on the backend configuration."""
        # Only use our API keys for these providers (to avoid leaking them to other backends)
        # TODO: add support for users to set their own API keys?

        if self.provider == "anthropic":
            assert self.base_url is None or self.base_url == "https://api.anthropic.com"
            assert self.api_key is None

            client = AsyncAnthropic(
                api_key=os.getenv("ANTHROPIC_API_KEY"),
                base_url=self.base_url,
            )
        else:
            # Custom provider
            client = AsyncAnthropic(
                api_key=self.api_key,
                base_url=self.base_url,
            )

        return ModelWithClient(
            client=client, model=self.model, max_tokens=self.max_tokens, thinking=self.thinking
        )
