import re
from abc import abstractmethod
from typing import Callable, Literal, Protocol

import anyio

from docent._log_util import get_logger
from docent_core._llm_util.data_models.llm_output import LLMOutput
from docent_core._llm_util.prod_llms import MessagesInput, get_llm_completions_async
from docent_core._llm_util.providers.preferences import PROVIDER_PREFERENCES, ModelOption

logger = get_logger(__name__)

ASSIGNMENT_PROMPT = """
You are given a detailed item A and a broader item B.
Your task is to perform membership testing: determine whether the description of A matches B.

Return two lines in the following exact format:
- ANSWER: <YES/NO>
- EXPLANATION: <concise but specific explanation; no more than a few high-information words>

Here is your input:
A: {item}
B: {cluster}
""".strip()


class AssignmentStreamingCallback(Protocol):
    async def __call__(
        self,
        batch_index: int,
        assignment: tuple[bool, str] | None,
    ) -> None: ...


def _parse_llm_output(output: LLMOutput):
    pattern = r"(?i)\s*-?\s*ANSWER:\s*(YES|NO)\s*\n\s*-?\s*EXPLANATION:\s*(.*)"
    match = re.search(pattern, output.first_text or "")

    if match:
        answer, explanation = match.groups()
        return (answer.strip().upper() == "YES", explanation.strip())

    return None


def _get_llm_streaming_callback(
    assignment_streaming_callback: AssignmentStreamingCallback,
):
    async def _streaming_callback(batch_index: int, llm_output: LLMOutput):
        assignment = _parse_llm_output(llm_output)
        await assignment_streaming_callback(batch_index, assignment)

    return _streaming_callback


class ClusterAssigner:
    def __init__(self, name: str):
        logger.info(f"Initializing assigner: {name}")
        self.name = name

    @abstractmethod
    async def skip_queries(self, items: list[str], cluster: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def assign(
        self,
        items: list[str],
        clusters: list[str],
        assignment_callback: AssignmentStreamingCallback | None = None,
    ) -> list[tuple[bool, str] | None]:
        """For each (item, cluster, attribute), determines whether
            `item` fits under `cluster` where `cluster` describes some `attribute` of `item`

        Args:
            items: The list of items to assign to clusters.
            clusters: The list of cluster descriptions (i.e., centroids).
        Returns:
            A list of boolean values indicating whether each item fits under each cluster.
        """

        raise NotImplementedError


class LlmApiClusterAssigner(ClusterAssigner):
    def __init__(
        self,
        system_prompt: str | None,
        model_options: list[ModelOption],
        max_new_tokens: int,
        temperature: float,
        assign_prompt_fn: Callable[[str, str], str] | None = None,
    ) -> None:
        super().__init__(f"llm-api-{'/'.join([o.model_name for o in model_options])}")
        self.system_prompt = system_prompt
        self.assign_prompt_fn = assign_prompt_fn
        self.model_options = model_options
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature

    @classmethod
    def from_o3_mini(cls, assign_prompt_fn: Callable[[str, str], str] | None = None):
        return cls(
            system_prompt=None,
            max_new_tokens=8192,
            temperature=1,
            model_options=PROVIDER_PREFERENCES.cluster_assign_o3_mini,
            assign_prompt_fn=assign_prompt_fn,
        )

    @classmethod
    def from_o4_mini(cls, assign_prompt_fn: Callable[[str, str], str] | None = None):
        return cls(
            system_prompt=None,
            max_new_tokens=8192,
            temperature=1,
            model_options=PROVIDER_PREFERENCES.cluster_assign_o4_mini,
            assign_prompt_fn=assign_prompt_fn,
        )

    @classmethod
    def from_sonnet_4_thinking(cls, assign_prompt_fn: Callable[[str, str], str] | None = None):
        return cls(
            system_prompt=None,
            max_new_tokens=4096,
            temperature=1.0,
            model_options=PROVIDER_PREFERENCES.cluster_assign_sonnet_4_thinking,
            assign_prompt_fn=assign_prompt_fn,
        )

    async def skip_queries(self, items: list[str], cluster: str) -> None:
        raise NotImplementedError

    @classmethod
    def from_gemini_flash(cls):
        return cls(
            system_prompt=None,
            max_new_tokens=8192,
            temperature=1.0,
            model_options=PROVIDER_PREFERENCES.cluster_assign_gemini_flash,
        )

    async def assign(
        self,
        items: list[str],
        clusters: list[str],
        assignment_callback: AssignmentStreamingCallback | None = None,
    ) -> list[tuple[bool, str] | None]:
        assert len(items) == len(
            clusters
        ), "Items, clusters, and attributes must be the same length"

        queries: list[MessagesInput] = [
            [
                *(
                    [{"role": "system", "content": self.system_prompt}]
                    if self.system_prompt
                    else []
                ),
                {
                    "role": "user",
                    "content": (
                        self.assign_prompt_fn(item, cluster)
                        if self.assign_prompt_fn
                        else ASSIGNMENT_PROMPT.format(item=item, cluster=cluster)
                    ),
                },
            ]
            for item, cluster in zip(items, clusters, strict=True)
        ]

        # Get the LLM callback if we're streaming
        llm_callback = (
            _get_llm_streaming_callback(assignment_callback)
            if assignment_callback is not None
            else None
        )

        outputs = await get_llm_completions_async(
            queries,
            model_options=self.model_options,
            max_new_tokens=self.max_new_tokens,
            temperature=self.temperature,
            timeout=30,
            completion_callback=llm_callback,
            use_cache=True,
        )
        return [_parse_llm_output(output) for output in outputs]


BaseAssignerType = Literal[
    "o3-mini", "o4-mini", "sonnet-4-thinking", "modernbert-ft", "gemini-flash"
]
BASE_ASSIGNERS: dict[BaseAssignerType, ClusterAssigner] = {}


async def _get_base_assigner(backend: BaseAssignerType) -> ClusterAssigner:
    if backend in BASE_ASSIGNERS:
        return BASE_ASSIGNERS[backend]

    async with anyio.Lock():
        if backend == "o3-mini":
            assigner = LlmApiClusterAssigner.from_o3_mini()
        elif backend == "o4-mini":
            assigner = LlmApiClusterAssigner.from_o4_mini()
        elif backend == "sonnet-4-thinking":
            assigner = LlmApiClusterAssigner.from_sonnet_4_thinking()
        elif backend == "gemini-flash":
            assigner = LlmApiClusterAssigner.from_gemini_flash()
        else:
            raise ValueError(f"Unknown backend: {backend}")

        BASE_ASSIGNERS[backend] = assigner
        return assigner


AssignerType = BaseAssignerType | Literal["hybrid"]
ASSIGNERS: dict[AssignerType, ClusterAssigner] = {}


async def get_assigner(backend: AssignerType) -> ClusterAssigner:
    if backend in ASSIGNERS:
        return ASSIGNERS[backend]

    async with anyio.Lock():
        if backend == "hybrid":
            raise NotImplementedError("Hybrid assigner not implemented")
        else:
            assigner = await _get_base_assigner(backend)

        ASSIGNERS[backend] = assigner
        return assigner


############
# Defaults #
############


async def assign_with_backend(
    backend: AssignerType,
    items: list[str],
    clusters: list[str],
    assignment_callback: AssignmentStreamingCallback | None = None,
) -> list[tuple[bool, str] | None]:
    assigner = await get_assigner(backend)
    return await assigner.assign(items, clusters, assignment_callback)


DEFAULT_ASSIGNER: AssignerType = "o4-mini"
