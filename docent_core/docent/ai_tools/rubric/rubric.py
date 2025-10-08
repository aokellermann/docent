import enum
import json
import time
from collections import Counter
from typing import Any, Callable, Literal, Protocol, cast
from uuid import uuid4

import anyio
import jsonschema
from pydantic import BaseModel, Field, field_serializer, field_validator
from tqdm.auto import tqdm

from docent._log_util import get_logger
from docent.data_models.agent_run import AgentRun
from docent.data_models.chat import ChatMessage
from docent.data_models.citation import parse_citations
from docent.data_models.remove_invalid_citation_ranges import remove_invalid_citation_ranges
from docent.data_models.transcript import TEXT_RANGE_CITE_INSTRUCTION
from docent_core._llm_util.data_models.exceptions import ValidationFailedException
from docent_core._llm_util.data_models.llm_output import LLMOutput
from docent_core._llm_util.providers.preferences import PROVIDER_PREFERENCES, ModelOption
from docent_core.docent.ai_tools.rubric.forgiving_json import forgiving_json_loads
from docent_core.docent.ai_tools.rubric.meta_schema import validate_judge_result_schema
from docent_core.docent.services.llms import LLMService

logger = get_logger(__name__)

RUBRIC_RESULT_EXPLANATION_INSTRUCTIONS = """
- Outside of citations, do not refer to transcript numbers or block numbers.
- Be concise. Focus on the most important aspects of the agent's behavior.
- Outside of citations, avoid quoting or paraphrasing the transcript. Focus on describing high-level patterns.
"""

RUBRIC_PROMPT = """
Here is a rubric that we are using to judge transcripts of AI agent runs.

Rubric:
{rubric}

Agent run:
{agent_run}

Your response should convey your judgment of the agent run according to the criteria given in the rubric \
provided above. Your entire response must be a valid JSON string which can be parsed with python `json.loads` \
without any additional processing.
The JSON object you produce must adhere to the following schema:
{output_schema}

Double quotes (`"`) in the middle of a string in the JSON object must be escaped with a backslash.
"""

DEFAULT_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "label": {"type": "string", "enum": ["match", "no match"]},
        "explanation": {"type": "string", "citations": True},
    },
    # Require these properties to be present
    "required": ["label", "explanation"],
    # Allow additional properties though, as their presence is not breaking
}

DEFAULT_JUDGE_MODEL = PROVIDER_PREFERENCES.default_judge_models[0]


def _schema_requests_citations(schema: dict[str, Any]) -> bool:
    """Check if any field in the schema requests citations by having 'citations': 'true'."""

    def _check_field(field_schema: Any) -> bool:
        if isinstance(field_schema, dict):
            if field_schema.get("citations"):  # type: ignore
                return True
            for value in field_schema.values():  # type: ignore
                if isinstance(value, dict) and _check_field(value):
                    return True
                elif isinstance(value, list):
                    for item in value:  # type: ignore
                        if isinstance(item, dict) and _check_field(item):
                            return True
        return False

    return _check_field(schema)


class Rubric(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    version: int = 1
    rubric_text: str
    judge_model: ModelOption = DEFAULT_JUDGE_MODEL
    output_schema: dict[str, Any] = DEFAULT_OUTPUT_SCHEMA

    @field_validator("output_schema")
    @classmethod
    def validate_output_schema(cls, output_schema: dict[str, Any]):
        """
        Raises:
            jsonschema.ValidationError: If the schema is invalid
            jsonschema.SchemaError: If the schema is not a valid 2020-12 schema
        """
        validate_judge_result_schema(output_schema)
        return output_schema


class ResultType(enum.Enum):
    """Enum for the type of result that a judge result can have."""

    DIRECT_RESULT = "direct_result"
    NEAR_MISS = "near_miss"


class JudgeResult(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    agent_run_id: str
    rubric_id: str
    rubric_version: int

    # Outputs
    output: dict[str, Any]
    result_metadata: dict[str, Any] | None = None
    result_type: ResultType

    # Deprecated
    value: str | None = None

    @field_serializer("result_type")
    def serialize_result_type(self, result_type: ResultType) -> str:
        return result_type.value


def _traverse_schema_and_transform(
    output: Any,
    schema: dict[str, Any],
    citation_string_handler: Callable[[str], Any],
) -> Any:
    """Recursively traverse output based on schema, applying citation_string_handler to citation strings."""
    if schema.get("type") == "string" and schema.get("citations"):  # type: ignore
        return citation_string_handler(output)
    elif schema.get("type") == "object":
        properties: dict[str, Any] = schema.get("properties", {})
        result: dict[str, Any] = {}
        for key in properties:
            if key in output:
                result[key] = _traverse_schema_and_transform(
                    output[key], properties[key], citation_string_handler
                )
        return result
    elif schema.get("type") == "array":
        item_schema: dict[str, Any] = schema.get("items", {})
        return [
            _traverse_schema_and_transform(item, item_schema, citation_string_handler)
            for item in output
        ]
    else:
        return output


class JudgeResultWithCitations(JudgeResult):
    @classmethod
    def from_judge_result(
        cls, result: JudgeResult, schema: dict[str, Any]
    ) -> "JudgeResultWithCitations":
        """Judge result must be validated against the schema before calling this function!"""

        def _parse_citation_string(output: str) -> dict[str, Any]:
            text, citations = parse_citations(output)
            return {"text": text, "citations": citations}

        data = result.model_dump()
        try:
            data["output"] = _traverse_schema_and_transform(
                data["output"], schema, _parse_citation_string
            )
        except Exception as e:
            logger.error(f"Failed to parse citations: {e}")
            logger.error(f"Output: {data['output']}")
            data["output"] = {"raw": data["output"]}
        return cls(**data)


class JudgeResultStreamingCallback(Protocol):
    """Supports batched streaming for cases where many search results are pre-computed.
    This avoids invoking the callback separately for each datapoint.
    """

    async def __call__(
        self,
        batch_index: int,
        judge_results: list[JudgeResult] | None,
    ) -> None: ...


def _validate_rubric_output(
    output: dict[str, Any], output_schema: dict[str, Any], agent_run: AgentRun
) -> dict[str, Any]:
    """Validate and filter citation text ranges in rubric results.

    Args:
        results: Raw results from LLM judge
        agent_run: Agent run containing transcript data for validation

    Returns:
        Validated result dict with invalid citations removed

    Raises:
        ValidationFailedException: If validation fails
    """

    def _validate_citation_string(text: str) -> str:
        validated_text = remove_invalid_citation_ranges(text, agent_run)
        if validated_text != text:
            logger.warning(
                f"Citation validation removed invalid text range from citation in judge result. "
                f"Agent run ID: {agent_run.id}, "
                f"Original text: {text}, "
                f"Validated text: {validated_text}, "
            )
        return validated_text

    try:
        jsonschema.validate(output, output_schema)
    except jsonschema.ValidationError as e:
        raise ValidationFailedException(f"Schema validation failed: {e}", failed_output=str(output))

    try:
        return _traverse_schema_and_transform(output, output_schema, _validate_citation_string)
    except Exception as e:
        raise ValidationFailedException(
            f"Citation validation failed: {e}", failed_output=str(output)
        )


def _parse_and_validate_llm_output(
    llm_output: LLMOutput,
    output_schema: dict[str, Any],
    agent_run: AgentRun,
) -> dict[str, Any]:
    """Parse and validate LLM output for rubric evaluation.

    Args:
        llm_output: The LLM output to parse
        output_schema: The schema to validate against
        agent_run: Agent run for citation validation

    Returns:
        Validated output dict

    Raises:
        ValidationFailedException: If parsing or validation fails
    """
    if llm_output.first_text is None:
        raise ValidationFailedException("LLM output has no text", failed_output=None)

    try:
        output = forgiving_json_loads(llm_output.first_text)
    except json.JSONDecodeError as e:
        raise ValidationFailedException(
            f"Failed to parse JSON: {e}. Raw text: `{llm_output.first_text}`",
            failed_output=llm_output.first_text,
        )

    if not isinstance(output, dict):
        logger.error(f"Expected dict output, got {type(output)}")
        logger.error(f"LLM output: {llm_output.first_text}")
        raise ValidationFailedException(
            f"Expected dict output, got {type(output)}. Raw text: {llm_output.first_text}",
            failed_output=llm_output.first_text,
        )

    return _validate_rubric_output(cast(dict[str, Any], output), output_schema, agent_run)


def construct_rubric_prompt(rubric: Rubric, agent_run: AgentRun, prompt_template: str) -> str:
    """Construct the full prompt text for rubric evaluation.

    This is the canonical implementation of prompt construction - use this function
    anywhere you need to construct a rubric evaluation prompt (including cost estimation).
    """
    output_schema_text = json.dumps(rubric.output_schema, indent=2)

    prompt = prompt_template.format(
        rubric=rubric.rubric_text,
        agent_run=agent_run.to_text_new(),
        output_schema=output_schema_text,
    )

    if _schema_requests_citations(rubric.output_schema):
        prompt += (
            "For strings which should contain citations (according to the schema) you must also follow these instructions: "
            + TEXT_RANGE_CITE_INSTRUCTION
            + RUBRIC_RESULT_EXPLANATION_INSTRUCTIONS
        )

    return prompt


def _get_prompt_resolver(rubric: Rubric, ar: AgentRun, prompt_template: str):
    def _prompt_resolver() -> list[ChatMessage | dict[str, Any]]:
        prompt = construct_rubric_prompt(rubric, ar, prompt_template)
        return [{"role": "user", "content": prompt}]

    return _prompt_resolver


def _parse_and_validate_output(
    output: str,
    rubric: Rubric,
    agent_run: AgentRun,
) -> dict[str, Any] | None:
    try:
        parsed_output = json.loads(output)
    except json.JSONDecodeError:
        logger.error(f"Failed to parse JSON for judge result:\n{output}")
        return None
    if not isinstance(parsed_output, dict):
        return None
    parsed_output = cast(dict[str, Any], parsed_output)

    # Validate dict against the output schema
    # This returns None if the output is invalid
    validated_output = _validate_rubric_output(parsed_output, rubric.output_schema, agent_run)

    return validated_output


def get_agreement_keys(schema: dict[str, Any]) -> list[str]:
    """Get list of top-level keys in schema that we want to measure agreement on.

    This includes enum, bool, and int fields. We skip float and strings.

    Args:
        schema: JSON schema dict

    Returns:
        List of field names (keys) that should be used for measuring agreement
    """
    agreement_keys: list[str] = []

    properties = schema.get("properties", {})
    assert isinstance(properties, dict)
    properties = cast(dict[str, Any], properties)

    for key, field_schema in properties.items():
        assert isinstance(field_schema, dict)
        field_schema = cast(dict[str, Any], field_schema)

        field_type = field_schema.get("type")
        assert isinstance(field_type, str)

        # Include boolean fields
        if field_type == "boolean":
            agreement_keys.append(key)
        # Include integer fields
        elif field_type == "integer":
            agreement_keys.append(key)
        # Include enum fields (even strings)
        elif "enum" in field_schema:
            agreement_keys.append(key)

    return agreement_keys


def find_modal_result(indep_results: list[dict[str, Any]], agreement_keys: list[str]):
    """Find the result that best matches modal values across agreement keys.

    Args:
        indep_results: List of independent results to analyze
        agreement_keys: Keys to measure agreement on

    Returns:
        Tuple of (max_idx, agt_key_modes_and_counts) where:
        - max_idx is the index of the result that best matches modal values
        - agt_key_modes_and_counts maps each key to (modal_value, count) or None if no values exist for that key

    Raises:
        ValueError: If no results are provided
    """
    if not indep_results:
        raise ValueError("No results to score")

    # For each agreement key, compute the mode and count (or None, if no values exist for that key)
    agt_key_modes_and_counts: dict[str, tuple[str | bool | int, int] | None] = {}
    for key in agreement_keys:
        key_modes = Counter(v for r in indep_results if (v := r.get(key)) is not None)
        if most_common_one := key_modes.most_common(1):
            agt_key_modes_and_counts[key] = most_common_one[0]
        else:
            agt_key_modes_and_counts[key] = None

    # Score each rollout based on how many agreement keys they match
    # If there is no mode for a key, or if a certain result doesn't have that key, it doesn't count.
    # TODO(mengk): This may bias towards results that have more keys.
    indep_result_scores: list[int] = []
    for r in indep_results:
        score = 0
        for key in agreement_keys:
            mode_and_count = agt_key_modes_and_counts[key]
            if mode_and_count and r.get(key) == mode_and_count[0]:
                score += 1
        indep_result_scores.append(score)

    # Argmax
    max_idx = indep_result_scores.index(max(indep_result_scores))

    return max_idx, agt_key_modes_and_counts


async def _evaluate_single_run_majority(
    *,
    agent_run: AgentRun,
    rubric: Rubric,
    rubric_prompt: str,
    llm_svc: LLMService,
    n_rollouts: int,
    result_type: ResultType,
    max_concurrency: int,
) -> JudgeResult | None:
    async def _validation_callback(batch_index: int, llm_output: LLMOutput):
        _parse_and_validate_llm_output(llm_output, rubric.output_schema, agent_run)

    prompt_resolver = _get_prompt_resolver(rubric, agent_run, rubric_prompt)
    outputs = await llm_svc.get_completions(
        inputs=[prompt_resolver for _ in range(n_rollouts)],
        model_options=[rubric.judge_model],
        max_new_tokens=16384,
        timeout=180.0,
        use_cache=False,
        validation_callback=_validation_callback,
        max_concurrency=max_concurrency,
    )

    # Process each rollout independently
    indep_results: list[dict[str, Any]] = []
    for output in outputs:
        if output.first_text is None:
            continue
        if validated_output := _parse_and_validate_output(output.first_text, rubric, agent_run):
            indep_results.append(validated_output)

    if not indep_results:
        return None

    # Get a list of the keys that we want to measure agreement on
    agreement_keys = get_agreement_keys(rubric.output_schema)

    # Find the result that best matches modal values
    final_max_idx, final_agt_key_modes_and_counts = find_modal_result(indep_results, agreement_keys)
    final_output = indep_results[final_max_idx]

    return JudgeResult(
        agent_run_id=agent_run.id,
        rubric_id=rubric.id,
        rubric_version=rubric.version,
        output=final_output,
        result_metadata={
            "agt_keys": agreement_keys,
            # Final measurements
            "final_results": indep_results,
            "final_agt_key_modes_and_counts": final_agt_key_modes_and_counts,
            "final_max_idx": final_max_idx,
        },
        result_type=result_type,
    )


async def _evaluate_single_run_multi_reflect(
    *,
    agent_run: AgentRun,
    rubric: Rubric,
    rubric_prompt: str,
    llm_svc: LLMService,
    n_rollouts: int,
    result_type: ResultType,
    max_concurrency: int,
) -> JudgeResult | None:
    async def _validation_callback(batch_index: int, llm_output: LLMOutput):
        _parse_and_validate_llm_output(llm_output, rubric.output_schema, agent_run)

    # Run several independent rollouts
    prompt_resolver = _get_prompt_resolver(rubric, agent_run, rubric_prompt)
    outputs = await llm_svc.get_completions(
        inputs=[prompt_resolver for _ in range(n_rollouts)],
        model_options=[rubric.judge_model],
        max_new_tokens=16384,
        timeout=180.0,
        use_cache=False,
        validation_callback=_validation_callback,
        max_concurrency=max_concurrency,
    )

    # Process each rollout
    indep_results: list[dict[str, Any]] = []
    for output in outputs:
        if output.first_text is None:
            continue
        if v_output := _parse_and_validate_output(output.first_text, rubric, agent_run):
            indep_results.append(v_output)

    if not indep_results:
        return None

    # Compute initial modes
    agreement_keys = get_agreement_keys(rubric.output_schema)
    indep_max_idx, indep_agt_key_modes_and_counts = find_modal_result(indep_results, agreement_keys)

    def _get_reflection_prompt_resolver(cur_index: int) -> Any:
        # Current result
        result = indep_results[cur_index]
        # Get other results (excluding the current one)
        other_results = [r for j, r in enumerate(indep_results) if j != cur_index]

        # Create the reflection message
        other_results_text = "\n\n".join(
            [f"Answer {j+1}:\n{json.dumps(r, indent=2)}" for j, r in enumerate(other_results)]
        )

        reflection_instruction = (
            f"Here are {len(other_results)} other independent answers to the same rubric evaluation:\n\n"
            f"{other_results_text}\n\n"
            f"Please reflect on these other answers and your own answer. "
            f"Consider if any of them have identified important aspects you missed, or if there are disagreements that should be resolved. "
            f"Then provide your final answer in the same JSON format as before."
        )

        def _prompt_resolver():
            """Function that lazily materializes the prompt, when the LLM is invoked."""

            # Construct the multi-message prompt
            # 1. Original user message
            # 2. Assistant message with the rollout's result
            # 3. New user message asking for reflection
            reflection_prompt = [
                *prompt_resolver(),  # Original user message(s)
                {"role": "assistant", "content": json.dumps(result, indent=2)},
                {"role": "user", "content": reflection_instruction},
            ]
            return reflection_prompt

        return _prompt_resolver

    final_results = indep_results.copy()  # Shallow copy
    if len(indep_results) > 1:
        # Ask the judge to reflect on the others' results
        reflection_outputs = await llm_svc.get_completions(
            inputs=[_get_reflection_prompt_resolver(i) for i in range(len(indep_results))],
            model_options=[rubric.judge_model],
            max_new_tokens=16384,
            timeout=180.0,
            use_cache=False,
            validation_callback=_validation_callback,
            max_concurrency=max_concurrency,
        )

        # Process reflection outputs in the same way as the initial rollouts
        reflected_results: list[dict[str, Any]] = []
        for output in reflection_outputs:
            if output.first_text is None:
                continue
            if v_output := _parse_and_validate_output(output.first_text, rubric, agent_run):
                reflected_results.append(v_output)

        # Use reflected results if we got any, otherwise fall back to original results
        if reflected_results:
            final_results = reflected_results

    final_max_idx, final_agt_key_modes_and_counts = find_modal_result(final_results, agreement_keys)
    return JudgeResult(
        agent_run_id=agent_run.id,
        rubric_id=rubric.id,
        rubric_version=rubric.version,
        output=final_results[final_max_idx],
        result_metadata={
            "agt_keys": agreement_keys,
            # Final measurements
            "final_results": final_results,
            "final_agt_key_modes_and_counts": final_agt_key_modes_and_counts,
            "final_max_idx": final_max_idx,
            # Also include initial measurements
            "indep_results": indep_results,
            "indep_max_idx": indep_max_idx,
            "indep_agt_key_modes_and_counts": indep_agt_key_modes_and_counts,
        },
        result_type=result_type,
    )


async def evaluate_rubric(
    agent_runs: list[AgentRun],
    rubric: Rubric,
    llm_svc: LLMService,
    callback: JudgeResultStreamingCallback | None = None,
    max_recall: bool = False,
    rollouts_per_input: int = 1,
    max_concurrent_llm_calls: int = 100,
    variant: Literal["majority", "multi-reflect"] = "majority",
):
    rubric_prompt = RUBRIC_MAX_RECALL_PROMPT if max_recall else RUBRIC_PROMPT
    result_type = ResultType.NEAR_MISS if max_recall else ResultType.DIRECT_RESULT

    if max_concurrent_llm_calls <= 0:
        raise ValueError("max_concurrent_llm_calls must be greater than 0")
    if rollouts_per_input <= 0:
        raise ValueError("rollouts_per_input must be greater than 0")

    max_concurrent_rubrics = max(1, max_concurrent_llm_calls // rollouts_per_input)
    semaphore = anyio.Semaphore(max_concurrent_rubrics)

    agent_results: list[JudgeResult | None] = [None for _ in agent_runs]
    progress_bar = tqdm(
        total=len(agent_runs),
        desc="Running rubric on agent runs",
        disable=not agent_runs,
    )

    async def _run_single_judge(index: int, agent_run: AgentRun):
        async with semaphore:
            if variant == "majority":
                fn = _evaluate_single_run_majority
            elif variant == "multi-reflect":
                fn = _evaluate_single_run_multi_reflect
            else:
                raise ValueError(f"Invalid variant: {variant}")

            start_perf_counter = time.perf_counter()
            result = await fn(
                agent_run=agent_run,
                rubric=rubric,
                rubric_prompt=rubric_prompt,
                llm_svc=llm_svc,
                n_rollouts=rollouts_per_input,
                result_type=result_type,
                max_concurrency=min(rollouts_per_input, max_concurrent_llm_calls),
            )
            duration_seconds = time.perf_counter() - start_perf_counter

        if result is not None:
            result = result.model_copy(
                update={
                    "result_metadata": (result.result_metadata or {})
                    | {"duration_seconds": duration_seconds}
                }
            )

        agent_results[index] = result

        if callback is not None:
            await callback(index, [result] if result is not None else None)
        progress_bar.update()

    try:
        async with anyio.create_task_group() as tg:
            for index, agent_run in enumerate(agent_runs):
                tg.start_soon(_run_single_judge, index, agent_run)
    finally:
        progress_bar.close()

    return agent_results


RUBRIC_MAX_RECALL_PROMPT = """
We are currently engaging in a rubric refinement process where a user comes in with a vague idea of a behavior they are looking for in a dataset of AI agent run transcripts. Our job is to collaborate with the user to write out a concrete specification of what they are looking for - i.e., create and refine a rubric.

This is challenging because the user themselves may not fully understand what they are looking for. Therefore, while we elicit the user's intent, we also may show them information that will change *their* conception of the goal. The general principle is that we want to extract maximum feedback from the user while requiring minimal effort on their part.

Their initial rubric was:
{rubric}

Here is one specific agent run:
{agent_run}

Your job is to find concrete examples of behavior in this agent run that might be clarifying or illuminating for the user to see.
- Instances that you would consider to match the rubric are excellent choices to show, so you can confirm that the user agrees with your judgments.
- Instances that you are uncertain about but think could plausibly match are also excellent because the user may find it useful to clarify ambiguous examples and see things that they may not have thought of themselves.
- It is also possible that you may not see anything that could plausibly be conceived of as the rubric.

Your output MUST adhere to the following schema:
{output_schema}
"""
