import enum
import re
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, Field, field_serializer

from docent._log_util import get_logger
from docent.data_models.agent_run import AgentRun
from docent.data_models.citation import Citation, parse_citations_single_run
from docent.data_models.transcript import SINGLE_RUN_CITE_INSTRUCTION
from docent_core._llm_util.data_models.llm_output import LLMOutput
from docent_core._llm_util.prod_llms import get_llm_completions_async
from docent_core._llm_util.providers.preferences import PROVIDER_PREFERENCES

logger = get_logger(__name__)


RUBRIC_PROMPT = f"""
You will be provided a rubric for something a user wants to find in an agent run. Your task is to check for occurrences of a rubric match in the provided run.

Rubric:
{{rubric}}

Agent run:
{{agent_run}}

First think carefully about whether the agent run contains any instances of the rubric. Guidelines:
- If something matches only an exclusion rule: NO, it should not be included.
- If something matches only an inclusion rule: YES, it should be included.
- If something matches both an inclusion and exclusion rule: YES, it should be included, since inclusion precedes exclusion.
- If something matches the high level description but no inclusion and no exclusion rules: YES, it should be included. Be proactive about looking for matches in this category, as they are very important.

It is possible that the agent does not exhibit the rubric behavior. If so, return N/A and nothing else; do not explain why there are no matches.

Otherwise, for every instance of a rubric match, describe how the agent run pertains to the rubric. Be concise but specific; I should be able to mentally reconstruct the pertinent parts of the run from your description. The list should also be exhaustive.

Return all instances of the rubric in the following exact format:
<instance>
description
</instance>
...
<instance>
description
</instance>

{SINGLE_RUN_CITE_INSTRUCTION}
"""


class Rubric(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    version: int = 1
    high_level_description: str
    inclusion_rules: list[str]
    exclusion_rules: list[str]

    @property
    def text(self) -> str:
        inclusion_text = "\n".join(f"- {rule}" for rule in self.inclusion_rules)
        exclusion_text = "\n".join(f"- {rule}" for rule in self.exclusion_rules)
        return f"(v{self.version}) High level description:\n{self.high_level_description}\n\nInclusion rules:\n{inclusion_text}\n\nExclusion rules:\n{exclusion_text}"


def _parse_rubric_outputs(output: LLMOutput) -> list[str] | None:
    if output.first_text is None:
        return None
    elif output.first_text.strip().upper() == "N/A":
        return []
    else:
        # Pattern matches text between <instance> and </instance> tags
        pattern = r"<instance>\n?(.*?)\n?</instance>"
        matches = re.finditer(pattern, output.first_text, re.DOTALL)
        return [str(match.group(1).strip()) for match in matches]


class ResultType(enum.Enum):
    """Enum for the type of result that a judge result can have."""

    DIRECT_RESULT = "direct_result"
    NEAR_MISS = "near_miss"


class JudgeResult(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    agent_run_id: str
    rubric_id: str
    rubric_version: int
    value: str | None = None
    result_type: ResultType

    @field_serializer("result_type")
    def serialize_result_type(self, result_type: ResultType) -> str:
        return result_type.value


class JudgeResultWithCitations(JudgeResult):
    citations: list[Citation] | None

    @classmethod
    def from_judge_result(cls, result: JudgeResult) -> "JudgeResultWithCitations":
        return cls(
            **result.model_dump(),
            citations=(
                parse_citations_single_run(result.value) if result.value is not None else None
            ),
        )


class JudgeResultStreamingCallback(Protocol):
    """Supports batched streaming for cases where many search results are pre-computed.
    This avoids invoking the callback separately for each datapoint.
    """

    async def __call__(
        self,
        batch_index: int,
        judge_results: list[JudgeResult] | None,
    ) -> None: ...


def _get_llm_callback(
    rubric_id: str,
    rubric_version: int,
    agent_run_ids: list[str],
    callback: JudgeResultStreamingCallback,
    result_type: ResultType,
):
    async def _llm_callback(batch_index: int, llm_output: LLMOutput):
        results = _parse_rubric_outputs(llm_output)

        # Return nothing if the LLM call failed (hence None)
        if results is None:
            await callback(batch_index, None)
        else:
            values: list[str | None] = results if len(results) > 0 else [None]  # type: ignore
            await callback(
                batch_index,
                [
                    JudgeResult(
                        agent_run_id=agent_run_ids[batch_index],
                        rubric_id=rubric_id,
                        rubric_version=rubric_version,
                        value=value,
                        result_type=result_type,
                    )
                    # If there were no matches, return a single None result
                    # Otherwise, return all results
                    for value in values
                ],
            )

    return _llm_callback


async def evaluate_rubric(
    agent_runs: list[AgentRun],
    rubric: Rubric,
    callback: JudgeResultStreamingCallback | None = None,
):
    ids = [ar.id for ar in agent_runs]
    texts = [ar.text for ar in agent_runs]

    prompts = [RUBRIC_PROMPT.format(rubric=rubric.text, agent_run=agent_run) for agent_run in texts]
    outputs = await get_llm_completions_async(
        [
            [
                {
                    "role": "user",
                    "content": prompt,
                },
            ]
            for prompt in prompts
        ],
        PROVIDER_PREFERENCES.evaluate_rubric,
        max_new_tokens=8192,
        timeout=180.0,
        use_cache=True,
        completion_callback=(
            _get_llm_callback(rubric.id, rubric.version, ids, callback, ResultType.DIRECT_RESULT)
            if callback is not None
            else None
        ),
    )

    ans: list[list[str] | None] = [
        None,
    ] * len(texts)
    for i, output in enumerate(outputs):
        ans[i] = _parse_rubric_outputs(output)

    return ans


RUBRIC_MAX_RECALL_PROMPT = f"""
We are currently engaging in a rubric refinement process where a user comes in with a vague idea of a behavior they are looking for in a dataset of AI agent run transcripts. Our job is to collaborate with the user to write out a concrete specification of what they are looking for - i.e., create and refine a rubric.

This is challenging because the user themselves may not fully understand what they are looking for. Therefore, while we elicit the user's intent, we also may show them information that will change *their* conception of the goal. The general principle is that we want to extract maximum feedback from the user while requiring minimal effort on their part.

Their initial rubric was:
<rubric>
{{rubric}}
</rubric>

Here is one specific agent run:
{{agent_run}}

Your job is to find concrete examples of behavior in this agent run that might be clarifying or illuminating for the user to see.
- Instances that you would consider to match the rubric are excellent choices to show, so you can confirm that the user agrees with your judgments.
- Instances that you are uncertain about but think could plausibly match are also excellent because the user may find it useful to clarify ambiguous examples and see things that they may not have thought of themselves.
- It is also possible that you may not see anything that could plausibly be conceived of as the rubric. In that case, you should just return N/A and do not include a final explanation.

Return all relevant instances of the rubric in the following exact format:
<instance>
...
</instance>
...

{SINGLE_RUN_CITE_INSTRUCTION}
"""


async def evaluate_rubric_max_recall(
    agent_runs: list[AgentRun],
    rubric: Rubric,
    callback: JudgeResultStreamingCallback | None = None,
):
    ids = [ar.id for ar in agent_runs]
    texts = [ar.text for ar in agent_runs]

    new_rubric = rubric.model_copy(deep=True)
    new_rubric.exclusion_rules = rubric.inclusion_rules + rubric.exclusion_rules
    new_rubric.inclusion_rules = []

    prompts = [
        RUBRIC_MAX_RECALL_PROMPT.format(
            rubric=new_rubric.text,
            agent_run=agent_run,
        )
        for agent_run in texts
    ]
    outputs = await get_llm_completions_async(
        [
            [
                {
                    "role": "user",
                    "content": prompt,
                },
            ]
            for prompt in prompts
        ],
        PROVIDER_PREFERENCES.evaluate_rubric_max_recall,
        max_new_tokens=8192,
        timeout=180.0,
        use_cache=True,
        completion_callback=(
            _get_llm_callback(rubric.id, rubric.version, ids, callback, ResultType.NEAR_MISS)
            if callback is not None
            else None
        ),
    )

    ans: list[list[str] | None] = [
        None,
    ] * len(texts)
    for i, output in enumerate(outputs):
        ans[i] = _parse_rubric_outputs(output)

    return ans
