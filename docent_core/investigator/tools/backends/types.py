"""Union types for different backend configurations."""

from typing import Literal, Union

from docent_core.investigator.tools.backends.anthropic_compatible_backend import (
    AnthropicCompatibleBackendConfig,
)
from docent_core.investigator.tools.backends.openai_compatible_backend import (
    OpenAICompatibleBackendConfig,
)

# Union type for all supported backend types
BackendConfig = Union[OpenAICompatibleBackendConfig, AnthropicCompatibleBackendConfig]

# Type literal for discriminating backend types
BackendType = Literal["openai_compatible", "anthropic_compatible"]
