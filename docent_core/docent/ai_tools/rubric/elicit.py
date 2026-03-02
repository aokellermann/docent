from __future__ import annotations

import json
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

import jsonschema
from pydantic import BaseModel, Field, ValidationError

from docent._llm_util.llm_svc import BaseLLMService
from docent._llm_util.providers.preference_types import ModelOption
from docent._log_util.logger import get_logger
from docent.data_models._tiktoken_util import get_token_count, truncate_to_token_limit
from docent.data_models.agent_run import AgentRun
from docent.data_models.citation import InlineCitation
from docent.judges.types import Rubric
from docent.judges.util.voting import (
    DistributionOutcome,
    OutputDistribution,
    assert_agreement_only_output_schema,
    normalize_output_distribution,
)
from docent.sdk.llm_context import LLMContext, resolve_citations_with_context
from docent_core.docent.ai_tools.rubric.user_model import (
    LabelingRequest,
    LabelingRequestFocusItem,
)

if TYPE_CHECKING:
    from docent_core.docent.ai_tools.rubric.user_model import (
        AgentRunFeedback,
        UserData,
    )

logger = get_logger(__name__)

# AGENT_RUN_TOK_LIMIT = 175_000
# DEFAULT_MODEL_OPTION = ModelOption(
#     provider="openrouter",
#     model_name="minimax/minimax-m2.5",
#     reasoning_effort=None,
# )
AGENT_RUN_TOK_LIMIT = 300_000
DEFAULT_MODEL_OPTION = ModelOption(
    provider="openrouter",
    model_name="openai/gpt-5.2",
    reasoning_effort=None,
)
# DEFAULT_MODEL_OPTION = ModelOption(
#     provider="openai",
#     model_name="gpt-5.2-2025-12-11",
#     reasoning_effort=None,
# )
# DEFAULT_MODEL_OPTION = ModelOption(
#     provider="anthropic",
#     model_name="claude-opus-4-5-20251101",
#     reasoning_effort=None,
# )
# DEFAULT_MODEL_OPTION = ModelOption(
#     provider="google",
#     model_name="gemini-3-flash-preview",
#     reasoning_effort=None,
# )
DEFAULT_USER_REASONING_FALLBACK = (
    "No explicit reasoning provided. This probability is inferred from the user context and "
    "available user QA/label history."
)
LABEL_METADATA_SEMANTICS_TEXT = (
    "IMPORTANT seed semantics:\n"
    "- In labeling_request.user_distribution and labeling_request.user_distribution_reasoning,\n"
    "  the p_u distribution/reasoning is the initial seed shown to the user before they\n"
    "  provided the final label.\n"
    "- This seed data is not user-authored text. User-authored signals are QA answers/explanations and\n"
    "  the final label explanation."
)
USER_DATA_PROMPT_TOKEN_LIMIT = 50_000
USER_DATA_SUMMARY_AGENT_RUN_TOK_LIMIT = 50_000
USER_DATA_SUMMARY_MAX_NEW_TOKENS = 4096


class RunDistributionEstimate(BaseModel):
    """Estimated user distribution for one run."""

    agent_run_id: str
    user_distribution: OutputDistribution | None = None
    reasoning: str | None = None
    reasoning_citations: list[InlineCitation] = Field(default_factory=list[InlineCitation])


class _RawDistributionOutcome(BaseModel):
    output: dict[str, Any]
    probability: object | None = None
    reasoning: str | None = None
    explanation: str | None = None


class _RawDistributionResponse(BaseModel):
    reasoning: str | None = None
    explanation: str | None = None
    outcomes: list[_RawDistributionOutcome] | None = None
    distribution: list[_RawDistributionOutcome] | None = None
    output: dict[str, Any] | None = None
    probability: object | None = None


def build_agent_run_dashboard_url(
    frontend_url: str,
    collection_id: str,
    agent_run_id: str,
) -> str:
    """Build the frontend URL for an agent run dashboard page."""
    normalized_frontend_url = frontend_url.rstrip("/")
    return f"{normalized_frontend_url}/dashboard/{collection_id}/agent_run/{agent_run_id}"


# === User Model Inference ===


@dataclass
class _UserDataSummaryTask:
    run_index: int
    agent_run_id: str


def _create_agent_run_feedback_summary_prompt(
    run_feedback: "AgentRunFeedback",
    agent_run_text: str,
) -> str:
    labeling_request = run_feedback.labeling_request
    review_focus_payload = [
        {
            "question": focus.question,
            "sample_answers": focus.sample_answers,
            "citations": [citation.model_dump(mode="json") for citation in focus.citations],
        }
        for focus in labeling_request.review_focus
    ]
    qa_pairs_payload = [
        {
            "question": qa_pair.focus_item.question,
            "sample_answers": qa_pair.focus_item.sample_answers,
            "selected_sample_index": qa_pair.selected_sample_index,
            "answer": qa_pair.answer,
            "explanation": qa_pair.explanation,
            "status": qa_pair.status,
            "is_custom_response": qa_pair.is_custom_response,
            "timestamp": qa_pair.timestamp.isoformat(),
        }
        for qa_pair in run_feedback.qa_pairs
    ]
    label_payload = _build_selected_label_payload(run_feedback) if run_feedback.label else None
    run_feedback_payload = {
        "run_title": labeling_request.title,
        "review_context": labeling_request.review_context,
        "review_context_citations": [
            citation.model_dump(mode="json")
            for citation in labeling_request.review_context_citations
        ],
        "review_focus": review_focus_payload,
        "qa_pairs": qa_pairs_payload,
        # Keep label at the end so the model sees it as the final source-of-truth decision.
        "label": label_payload,
    }
    run_feedback_payload_json = json.dumps(run_feedback_payload, indent=2)
    return f"""You are summarizing all human feedback for one agent run for user-context inference.

AGENT RUN CONTEXT:
{agent_run_text}

RUN FEEDBACK ENTRY:
{run_feedback_payload_json}

{LABEL_METADATA_SEMANTICS_TEXT}

Write a concrete, rich summary (6-10 sentences) that captures:
- the relevant run context (what happened and why this case matters),
- how the user responded across the QA pairs (including extra context if provided),
- the user's final label decision for this run (place this near the end of your summary; include
  label values and explanation if provided),
- whether the user appears to agree or disagree with the initial p_u seed distribution/reasoning
  and what parts of that seed reasoning they seem to respond to,
- what this combined feedback suggests about this user's rubric reasoning in this case.

Stay grounded in specific details from this run and this feedback entry. Do not write abstract
principles.

Return only:
<summary>
[your summary]
</summary>
"""


def _extract_summary_text(raw_response: str) -> str:
    match = re.search(r"<summary>(.*?)</summary>", raw_response, re.DOTALL)
    if match:
        return match.group(1).strip()
    return raw_response.strip()


def _build_selected_label_payload(run_feedback: "AgentRunFeedback") -> dict[str, Any]:
    labeled_run = run_feedback.label
    if labeled_run is None:
        raise ValueError("run_feedback.label must be present for selected label payload")

    user_distribution = run_feedback.labeling_request.user_distribution
    return {
        "label_value": labeled_run.label_value,
        "explanation": labeled_run.explanation,
        "user_distribution": (
            user_distribution.model_dump(mode="json") if user_distribution is not None else None
        ),
        "user_distribution_reasoning": run_feedback.labeling_request.user_distribution_reasoning,
    }


def _format_label_evidence_block(run_feedback: "AgentRunFeedback") -> str:
    payload = _build_selected_label_payload(run_feedback)
    label_value = cast(dict[str, Any], payload["label_value"])
    label_value_text = json.dumps(label_value, sort_keys=True)

    user_distribution_payload = payload.get("user_distribution")
    user_distribution_text = (
        json.dumps(user_distribution_payload, sort_keys=True)
        if isinstance(user_distribution_payload, dict)
        else "N/A"
    )

    user_distribution_reasoning = payload.get("user_distribution_reasoning")
    user_distribution_reasoning_text = (
        user_distribution_reasoning.strip()
        if isinstance(user_distribution_reasoning, str) and user_distribution_reasoning.strip()
        else "N/A"
    )

    explanation = payload.get("explanation")
    explanation_text = (
        explanation.strip() if isinstance(explanation, str) and explanation.strip() else "N/A"
    )

    return (
        "User-provided label:\n"
        f"User label: {label_value_text}\n"
        f"User explanation: {explanation_text}\n"
        "p_u distribution (initial seed shown before final label; not user-authored): "
        f"{user_distribution_text}\n"
        "p_u reasoning (initial seed shown before final label; not user-authored): "
        f"{user_distribution_reasoning_text}"
    )


def _format_run_feedback_qa_evidence_block(run_feedback: "AgentRunFeedback") -> str:
    lines = ["User-provided question/answer pairs:"]
    if not run_feedback.qa_pairs:
        lines.append("None recorded for this run.")
        return "\n".join(lines)

    for qa_idx, qa_pair in enumerate(run_feedback.qa_pairs):
        qa_tag = f"qa_{qa_idx + 1}"
        lines.extend(
            [
                f"<{qa_tag}>",
                f"Question: {qa_pair.focus_item.question}",
                f"User answer: {qa_pair.answer}",
                f"User explanation: {qa_pair.explanation or 'N/A'}",
                f"Status: {qa_pair.status}",
                f"</{qa_tag}>",
            ]
        )
    return "\n".join(lines)


def _build_generated_user_data_summary_text(
    run_blocks: list[str],
    total_feedback_units: int,
    total_source_qa_pairs: int,
    total_labels: int,
) -> str:
    run_section = "\n\n".join(run_blocks) if run_blocks else "No run summaries."
    return (
        f"Run Summaries ({len(run_blocks)}/{total_feedback_units} shown):\n{run_section}\n\n"
        f"Source feedback totals: {total_source_qa_pairs} QA pair(s), {total_labels} label(s).\n\n"
        f"{LABEL_METADATA_SEMANTICS_TEXT}"
    )


def _fit_generated_user_data_summary_to_token_limit(
    run_blocks: list[str],
    total_feedback_units: int,
    total_source_qa_pairs: int,
    total_labels: int,
    max_tokens: int,
) -> tuple[str, int]:
    included_runs: list[str] = []

    for run_block in run_blocks:
        candidate = _build_generated_user_data_summary_text(
            run_blocks=included_runs + [run_block],
            total_feedback_units=total_feedback_units,
            total_source_qa_pairs=total_source_qa_pairs,
            total_labels=total_labels,
        )
        if get_token_count(candidate) <= max_tokens:
            included_runs.append(run_block)
            continue
        break

    summary = _build_generated_user_data_summary_text(
        run_blocks=included_runs,
        total_feedback_units=total_feedback_units,
        total_source_qa_pairs=total_source_qa_pairs,
        total_labels=total_labels,
    )
    omitted_feedback_units = total_feedback_units - len(included_runs)
    return summary, omitted_feedback_units


async def summarize_user_data_for_prompt_with_agent_runs(
    user_data: "UserData",
    agent_runs_by_id: dict[str, AgentRun],
    llm_svc: BaseLLMService,
    max_tokens: int = USER_DATA_PROMPT_TOKEN_LIMIT,
    log_truncation_warning: bool = True,
) -> str:
    if max_tokens <= 0:
        raise ValueError("max_tokens must be > 0")

    feedback_units = user_data.agent_run_feedbacks
    total_feedback_units = len(feedback_units)
    total_source_qa_pairs = sum(len(feedback.qa_pairs) for feedback in feedback_units)
    total_labels = sum(1 for feedback in feedback_units if feedback.label is not None)

    inputs: list[list[dict[str, str]]] = []
    summary_tasks: list[_UserDataSummaryTask] = []

    for run_idx, run_feedback in enumerate(feedback_units):
        agent_run = agent_runs_by_id.get(run_feedback.agent_run_id)
        if agent_run is None:
            logger.error(
                "Skipping feedback unit %d for user-data summary; missing agent run %s",
                run_idx + 1,
                run_feedback.agent_run_id,
            )
            continue

        agent_run_text = LLMContext(items=[agent_run]).to_str()
        agent_run_text, _, _ = truncate_to_token_limit(
            agent_run_text, max_tokens=USER_DATA_SUMMARY_AGENT_RUN_TOK_LIMIT
        )
        prompt = _create_agent_run_feedback_summary_prompt(
            run_feedback=run_feedback,
            agent_run_text=agent_run_text,
        )
        inputs.append([{"role": "user", "content": prompt}])
        summary_tasks.append(
            _UserDataSummaryTask(
                run_index=run_idx,
                agent_run_id=run_feedback.agent_run_id,
            )
        )

    run_blocks: list[str] = []

    if inputs:
        outputs = await llm_svc.get_completions(
            inputs=inputs,
            model_options=[DEFAULT_MODEL_OPTION],
            max_new_tokens=USER_DATA_SUMMARY_MAX_NEW_TOKENS,
            temperature=0.2,
            timeout=120.0,
        )

        for summary_task, output in zip(summary_tasks, outputs):
            if output.did_error:
                logger.error(
                    "Failed to summarize user-data feedback unit %d for run %s: %s",
                    summary_task.run_index + 1,
                    summary_task.agent_run_id,
                    output.errors,
                )
                continue

            response_text = output.completions[0].text if output.completions else ""
            summary_text = _extract_summary_text(response_text or "")
            if not summary_text:
                logger.error(
                    "Failed to summarize user-data feedback unit %d for run %s: empty summary",
                    summary_task.run_index + 1,
                    summary_task.agent_run_id,
                )
                continue

            run_feedback = feedback_units[summary_task.run_index]
            qa_evidence_entry = _format_run_feedback_qa_evidence_block(run_feedback)
            label_evidence_entry = (
                _format_label_evidence_block(run_feedback)
                if run_feedback.label is not None
                else (
                    "User-provided label:\n"
                    "User label: N/A\n"
                    "User explanation: N/A\n"
                    "p_u distribution and reasoning "
                    "(initial seed shown before final label; not user-authored): N/A"
                )
            )
            run_blocks.append(
                (
                    f"--- Run Summary {summary_task.run_index + 1} "
                    f"(run: {summary_task.agent_run_id}) ---\n"
                    f"Generated contextual summary:\n{summary_text}\n\n"
                    f"{qa_evidence_entry}\n\n"
                    f"{label_evidence_entry}\n\n"
                    f"QA pairs in this feedback unit: {len(run_feedback.qa_pairs)}"
                )
            )

    summary, omitted_feedback_units = _fit_generated_user_data_summary_to_token_limit(
        run_blocks=run_blocks,
        total_feedback_units=total_feedback_units,
        total_source_qa_pairs=total_source_qa_pairs,
        total_labels=total_labels,
        max_tokens=max_tokens,
    )
    used_tokens = get_token_count(summary)

    logger.info(
        (
            "Built agent-run user-data summary for prompt: %d/%d tokens, "
            "%d/%d run summaries included, source totals %d QA pair(s), %d label(s)"
        ),
        used_tokens,
        max_tokens,
        total_feedback_units - omitted_feedback_units,
        total_feedback_units,
        total_source_qa_pairs,
        total_labels,
    )

    if log_truncation_warning and omitted_feedback_units > 0:
        logger.warning(
            (
                "Agent-run user-data summary hit token or availability limits (%d/%d). "
                "Omitted %d feedback unit(s) from prompt context."
            ),
            used_tokens,
            max_tokens,
            omitted_feedback_units,
        )

    return summary


def _create_user_context_inference_prompt(
    initial_rubric: str,
    user_data_summary: str,
) -> str:
    return f"""You are building a user context for rubric-based labeling. The context should be a **curated collection of richly annotated examples** that a downstream LLM can reason from by analogy — NOT a set of abstract principles.

INITIAL RUBRIC:
{initial_rubric}

OBSERVED USER DATA:
{user_data_summary}

Your task: Transform the observed data into a set of annotated examples that capture how this user thinks.

OUTPUT FORMAT — use this structure exactly:

Start with a concise orientation section:

### High-level user orientation
[2-4 sentences on what the user seems to optimize for overall, what they are trying to avoid, and any major tradeoff they repeatedly make.]

Then, for each meaningful piece of feedback, produce an entry:

### Example N: [short descriptive title]
**Situation:** [Rich description of the context — what the agent did, what the task was, what happened. Preserve concrete details.]
**Question:** [The question that was asked]
**User's judgment:** [The user's full answer, including any extra context they provided]
**What this reveals:** [1-2 concrete sentences about what this specific case tells us about the user's preferences. Stay grounded in this example — do NOT generalize into abstract principles.]

After all examples, include ONE brief section:

### Connecting patterns
- [2-4 bullets, each citing specific example numbers, e.g. "Examples 3 and 7 both show the user cares about X when Y happens"]

CRITICAL RULES:
- The "High-level user orientation" must be at the top and stay succinct (2-4 sentences).
- The annotated examples should comprise ~80% of the output. Do NOT abstract them away into principles.
- Preserve rich situational detail — the downstream LLM needs enough context to reason by analogy to new cases.
- If two examples seem contradictory, keep BOTH and note the tension in "What this reveals."
- The "Connecting patterns" section should be SHORT (2-4 bullets). It exists to help orient a reader, not to replace the examples.
- Treat each "User-provided label" block as source-of-truth for what the user ultimately decided.
- In a "User-provided label" block, "p_u distribution and reasoning" is metadata from the initial p_u judge seed shown before labeling, not what the user said. Use this to analyze agreement/disagreement with the final user label/explanation and what seed reasoning the user appears to accept or reject.
- Do not contradict or overwrite user-provided wording; when referencing user-stated explanation text, quote it exactly.

Return your response in this format:
<user_context>
[Your example-based user context in markdown]
</user_context>
"""


async def build_user_context_inference_prompt_with_agent_runs(
    user_data: "UserData",
    agent_runs_by_id: dict[str, AgentRun],
    llm_svc: BaseLLMService,
    max_tokens: int = USER_DATA_PROMPT_TOKEN_LIMIT,
    log_truncation_warning: bool = True,
) -> tuple[str, str]:
    """Render user-data summary and inference prompt using AgentRun-grounded summaries."""
    user_data_summary = await summarize_user_data_for_prompt_with_agent_runs(
        user_data=user_data,
        agent_runs_by_id=agent_runs_by_id,
        llm_svc=llm_svc,
        max_tokens=max_tokens,
        log_truncation_warning=log_truncation_warning,
    )
    prompt = _create_user_context_inference_prompt(
        initial_rubric=user_data.initial_rubric,
        user_data_summary=user_data_summary,
    )
    return user_data_summary, prompt


async def infer_user_context_from_user_data(
    user_data: "UserData",
    llm_svc: BaseLLMService,
    user_data_summary: str,
) -> str:
    """Infer textual user context c from a provided user-data summary."""
    has_answered_qa = any(True for _ in user_data.iter_answered_qa_entries())
    has_labels = any(True for _ in user_data.iter_labeled_entries())
    if not has_answered_qa and not has_labels:
        return user_data.initial_rubric

    prompt = _create_user_context_inference_prompt(
        initial_rubric=user_data.initial_rubric,
        user_data_summary=user_data_summary,
    )

    outputs = await llm_svc.get_completions(
        inputs=[[{"role": "user", "content": prompt}]],
        model_options=[DEFAULT_MODEL_OPTION],
        max_new_tokens=8192,
        timeout=120.0,
    )
    output = outputs[0]

    if output.did_error:
        logger.warning(f"Failed to infer user context from user data: {output.errors}")
        return user_data.initial_rubric

    response_text = output.completions[0].text or ""
    match = re.search(r"<user_context>(.*?)</user_context>", response_text, re.DOTALL)
    if match:
        return match.group(1).strip()

    stripped = response_text.strip()
    return stripped or user_data.initial_rubric


def create_user_distribution_prompt(
    agent_run_text: str,
    rubric_text: str,
    output_schema: dict[str, Any],
    user_context_text: str,
    citation_instructions: str,
) -> str:
    """Create prompt for p_u(y | x, c, r)."""
    schema_text = json.dumps(output_schema, indent=2)

    return f"""You are estimating p_u(y | x, c, r), where y follows the rubric output schema.

{citation_instructions}

Rubric:
{rubric_text}

Output schema:
{schema_text}

User context c:
{user_context_text}

Agent run:
{agent_run_text}

Task:
Given the user context, what would you anticipate the user says?
Estimate the distribution using this reasoning procedure:
1. Reason through the rubric as applied to this specific agent run, using user context c as your evidence base.
2. While reasoning, explicitly track uncertainties that matter for the rubric outcome.
3. For each uncertainty, assess evidence coverage in c:
   - If c has relevant direct/indirect/conflicting evidence, treat it as partially informed (less uncertain).
   - If c does not address it, treat it as unaddressed (more uncertain).
4. At the end, synthesize uncertainties into a short set of generalized key cruxes (not overfit to this one run), where each crux is written as a concrete, operationalized question that is understandable without reading this specific agent run.
5. For each key crux question, describe how the output distribution would shift if the crux resolved one way vs the opposite way.
6. Holistically synthesize all cruxes and evidence to produce the final probability distribution.

Guidance:
- Anchor reasoning to rubric-relevant factors only.
- Prefer concrete evidence from c over speculation.
- Explicitly note unresolved, sparse, missing, or conflicting evidence and how it changes uncertainty.
- Distinguish clearly between "partially informed" uncertainty vs "unaddressed" uncertainty.
- Key cruxes should be abstract enough to generalize to similar cases.
- Each key crux must be phrased as a concrete, operationalized, mostly self-contained question with clearly defined opposite resolutions, such that a reader who has not read this specific agent run can still understand what the question means.
- Include counterfactual distribution impacts for each crux ("if resolved A vs B, probability mass moves how?").
- Connect the final distribution to specific user-context signals.
- Probabilities should sum to 1.
- Keep the JSON schema exactly as specified.

Return JSON:
{{
  "reasoning": "<rubric-grounded reasoning with uncertainty tracking, ending in generalized key crux questions and their counterfactual distribution impacts>",
  "outcomes": [
    {{
      "output": <json object compliant with schema>,
      "probability": <float>
    }}
  ]
}}
"""


def parse_output_distribution_response(
    llm_response: str,
    context: LLMContext | None,
    output_schema: dict[str, Any],
    require_reasoning: bool = False,
    missing_reasoning_fallback: str = DEFAULT_USER_REASONING_FALLBACK,
) -> tuple[OutputDistribution, str | None, list[InlineCitation]] | None:
    """Parse distribution JSON from LLM response, resolve citations, normalize probabilities."""
    parsed = parse_llm_json_response(llm_response, keys=("outcomes", "distribution", "output"))
    if parsed is None:
        return None

    try:
        parsed_distribution = _RawDistributionResponse.model_validate(parsed)
    except ValidationError:
        return None

    overall_reasoning = parsed_distribution.reasoning or parsed_distribution.explanation

    raw_outcomes = parsed_distribution.outcomes or parsed_distribution.distribution
    if raw_outcomes is None and parsed_distribution.output is not None:
        raw_outcomes = [
            _RawDistributionOutcome(
                output=parsed_distribution.output,
                probability=parsed_distribution.probability,
                reasoning=parsed_distribution.reasoning,
                explanation=parsed_distribution.explanation,
            )
        ]

    if raw_outcomes is None:
        return None

    extracted_outputs: list[dict[str, Any]] = []
    extracted_probs: list[float | None] = []
    outcome_reasoning: list[str] = []

    for raw_outcome in raw_outcomes:
        if overall_reasoning is None:
            outcome_reasoning_text = raw_outcome.reasoning or raw_outcome.explanation
            if isinstance(outcome_reasoning_text, str) and outcome_reasoning_text.strip():
                outcome_reasoning.append(outcome_reasoning_text.strip())

        try:
            jsonschema.validate(raw_outcome.output, output_schema)
        except (jsonschema.ValidationError, jsonschema.SchemaError):
            return None

        extracted_outputs.append(raw_outcome.output)
        extracted_probs.append(_coerce_probability(raw_outcome.probability))

    if not extracted_outputs:
        return None

    if overall_reasoning is None and outcome_reasoning:
        overall_reasoning = outcome_reasoning[0]

    overall_reasoning_citations: list[InlineCitation] = []
    if overall_reasoning and context is not None:
        overall_reasoning, overall_reasoning_citations = resolve_citations_with_context(
            overall_reasoning, context, validate_text_ranges=True
        )

    if require_reasoning and (not overall_reasoning or not overall_reasoning.strip()):
        overall_reasoning = missing_reasoning_fallback

    assign_uniform = any(prob is None for prob in extracted_probs)
    probabilities: list[float] = []
    if assign_uniform:
        uniform = 1.0 / len(extracted_outputs)
        probabilities = [uniform] * len(extracted_outputs)
    else:
        concrete_probs = [prob for prob in extracted_probs if prob is not None]
        total = sum(concrete_probs)
        if total <= 0:
            uniform = 1.0 / len(extracted_outputs)
            probabilities = [uniform] * len(extracted_outputs)
        else:
            probabilities = [prob / total for prob in concrete_probs]

    outcomes = [
        DistributionOutcome(
            output=output,
            probability=prob,
        )
        for output, prob in zip(
            extracted_outputs,
            probabilities,
        )
    ]

    distribution = normalize_output_distribution(OutputDistribution(outcomes=outcomes))
    return distribution, overall_reasoning, overall_reasoning_citations


async def estimate_user_distributions_for_agent_runs(
    agent_runs: list[AgentRun],
    rubric: Rubric,
    user_context_text: str,
    llm_svc: BaseLLMService,
) -> list[RunDistributionEstimate]:
    """Estimate p_u for each run using only the inferred user context."""
    assert_agreement_only_output_schema(rubric.output_schema)

    if not agent_runs:
        return []

    user_inputs: list[list[dict[str, str]]] = []
    run_metadata: list[tuple[str, LLMContext]] = []

    for agent_run in agent_runs:
        context = LLMContext(items=[agent_run])
        citation_instructions = context.get_system_message(
            interactive=False, include_citations=True
        )
        agent_run_text = context.to_str()
        agent_run_text, _, _ = truncate_to_token_limit(
            agent_run_text, max_tokens=AGENT_RUN_TOK_LIMIT
        )

        user_prompt = create_user_distribution_prompt(
            agent_run_text=agent_run_text,
            rubric_text=rubric.rubric_text,
            output_schema=rubric.output_schema,
            user_context_text=user_context_text,
            citation_instructions=citation_instructions,
        )

        user_inputs.append([{"role": "user", "content": user_prompt}])
        run_metadata.append((agent_run.id, context))

    user_outputs = await llm_svc.get_completions(
        inputs=user_inputs,
        model_options=[DEFAULT_MODEL_OPTION],
        max_new_tokens=8192,
        temperature=1.0,
        timeout=180.0,
    )

    results: list[RunDistributionEstimate] = []
    for (agent_run_id, context), user_output in zip(run_metadata, user_outputs):
        if user_output.did_error:
            logger.warning(
                "User distribution error for run %s: %s",
                agent_run_id,
                "; ".join(str(e) for e in user_output.errors),
            )
            results.append(RunDistributionEstimate(agent_run_id=agent_run_id))
            continue

        user_text = user_output.completions[0].text or ""
        parsed_distribution = parse_output_distribution_response(
            user_text,
            context=context,
            output_schema=rubric.output_schema,
            require_reasoning=True,
            missing_reasoning_fallback=DEFAULT_USER_REASONING_FALLBACK,
        )

        if parsed_distribution is None:
            logger.warning("Failed to parse user distribution response for run %s", agent_run_id)
            results.append(RunDistributionEstimate(agent_run_id=agent_run_id))
            continue
        user_distribution, reasoning, reasoning_citations = parsed_distribution

        results.append(
            RunDistributionEstimate(
                agent_run_id=agent_run_id,
                user_distribution=user_distribution,
                reasoning=reasoning,
                reasoning_citations=reasoning_citations,
            )
        )

    valid_estimates = [estimate for estimate in results if estimate.user_distribution is not None]
    logger.info(
        "Finished sampled user distribution estimates: %d total, %d valid.",
        len(results),
        len(valid_estimates),
    )
    return results


# === Labeling Request Generation ===


def _distribution_summary_for_prompt(
    distribution: OutputDistribution,
    reasoning: str | None,
    max_outcomes: int = 5,
) -> str:
    return format_user_distribution_for_display(
        distribution=distribution,
        reasoning=reasoning,
        max_outcomes=max_outcomes,
        max_reasoning_chars=220,
    )


def format_user_distribution_for_display(
    distribution: OutputDistribution,
    reasoning: str | None = None,
    max_outcomes: int = 5,
    max_reasoning_chars: int | None = None,
) -> str:
    """Render normalized p_u outcomes and reasoning as pretty JSON for display."""
    normalized = normalize_output_distribution(distribution)
    payload_outcomes: list[dict[str, Any]] = []
    for outcome in normalized.outcomes[:max_outcomes]:
        payload_outcomes.append(
            {
                "output": outcome.output,
                "probability": round(outcome.probability, 6),
            }
        )

    reasoning_text = reasoning or ""
    if max_reasoning_chars is not None:
        reasoning_text = _truncate_for_prompt(reasoning_text, max_reasoning_chars)

    payload: dict[str, Any] = {"reasoning": reasoning_text, "outcomes": payload_outcomes}
    return json.dumps(payload, indent=2)


def _inline_citation_identity_key(citation: InlineCitation) -> str:
    return json.dumps(
        citation.target.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )


def _format_inline_citation_target(citation: InlineCitation, max_snippet_chars: int) -> str:
    target = citation.target.item
    item_type = getattr(target, "item_type", "unknown")
    details: list[str] = []

    transcript_id = getattr(target, "transcript_id", None)
    if transcript_id is not None:
        details.append(str(transcript_id))

    block_idx = getattr(target, "block_idx", None)
    if block_idx is not None:
        details.append(f"B{block_idx}")

    content_idx = getattr(target, "content_idx", None)
    if content_idx is not None:
        details.append(f"C{content_idx}")

    metadata_key = getattr(target, "metadata_key", None)
    if metadata_key is not None:
        details.append(f"M.{metadata_key}")

    result_set_id = getattr(target, "result_set_id", None)
    if result_set_id is not None:
        details.append(f"set:{result_set_id}")

    result_id = getattr(target, "result_id", None)
    if result_id is not None:
        details.append(f"result:{result_id}")

    if not details:
        agent_run_id = getattr(target, "agent_run_id", None)
        if agent_run_id is not None:
            details.append(str(agent_run_id))

    target_text = item_type if not details else f"{item_type}:{':'.join(details)}"

    text_range = citation.target.text_range
    snippet = text_range.start_pattern if text_range is not None else None
    if snippet is None:
        return target_text

    snippet_text = " ".join(snippet.split())
    if len(snippet_text) > max_snippet_chars:
        snippet_text = snippet_text[:max_snippet_chars] + "..."
    if not snippet_text:
        return target_text
    return f'{target_text} | "{snippet_text}"'


def render_text_with_citation_footnotes(
    text: str,
    citations: Sequence[InlineCitation],
    max_snippet_chars: int = 120,
) -> tuple[str, list[str]]:
    """Replace inline citation spans with numeric references and section footnotes."""
    if not citations:
        return text, []

    sorted_citations = sorted(citations, key=lambda cite: (cite.start_idx, cite.end_idx))
    rendered_parts: list[str] = []
    identity_to_number: dict[str, int] = {}
    footnotes_by_number: dict[int, str] = {}

    cursor = 0
    text_len = len(text)
    next_number = 1
    for citation in sorted_citations:
        start_idx = citation.start_idx
        end_idx = citation.end_idx
        if start_idx < 0 or end_idx > text_len or start_idx >= end_idx:
            continue
        if start_idx < cursor:
            # Ignore conflicting/overlapping spans and keep deterministic output.
            continue

        rendered_parts.append(text[cursor:start_idx])

        citation_key = _inline_citation_identity_key(citation)
        citation_number = identity_to_number.get(citation_key)
        if citation_number is None:
            citation_number = next_number
            identity_to_number[citation_key] = citation_number
            footnotes_by_number[citation_number] = _format_inline_citation_target(
                citation=citation,
                max_snippet_chars=max_snippet_chars,
            )
            next_number += 1

        rendered_parts.append(f"[{citation_number}]")
        cursor = end_idx

    rendered_parts.append(text[cursor:])
    rendered_text = "".join(rendered_parts)
    footnotes = [f"[{idx}] {footnotes_by_number[idx]}" for idx in range(1, next_number)]
    return rendered_text, footnotes


def normalize_sample_answers(raw_sample_answers: object, max_items: int = 3) -> list[str]:
    """Normalize sample answer choices to unique, non-empty strings."""
    if not isinstance(raw_sample_answers, list):
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for raw_item in cast(list[object], raw_sample_answers):
        if not isinstance(raw_item, str):
            continue
        stripped = raw_item.strip()
        if not stripped or stripped in seen:
            continue
        normalized.append(stripped)
        seen.add(stripped)
        if len(normalized) >= max_items:
            break
    return normalized


def create_labeling_request_prompt(
    agent_run_text: str,
    citation_instructions: str,
    rubric_text: str,
    rubric_output_schema: dict[str, Any],
    user_context_text: str,
    user_distribution: OutputDistribution,
    user_distribution_reasoning: str | None = None,
    priority_score: float | None = None,
    priority_metric_name: str = "H[p_u]",
) -> str:
    """Create prompt for constructing a user-facing labeling request with citations."""
    user_summary = _distribution_summary_for_prompt(
        distribution=user_distribution,
        reasoning=user_distribution_reasoning,
    )
    rubric_schema_text = json.dumps(rubric_output_schema, indent=2, sort_keys=True)
    priority_score_text = f"{priority_score:.6f}" if priority_score is not None else "N/A"

    return f"""You are preparing a human labeling request for an AI agent run.

{citation_instructions}

Background:
We are running an active learning loop to elicit a user's rubric for evaluating agent runs.
- c is the current user context: a summary of the user's known preferences and evaluation criteria.
- p_u(y | x, c, r) is the anticipated user distribution, predicted from c.
- The run is prioritized when p_u indicates high uncertainty, because labeling this case is likely to improve the user context.

Original rubric r (source of truth for what should be evaluated):
{rubric_text}

Rubric output schema (allowed label fields):
{rubric_schema_text}

User context c:
{user_context_text}

Anticipated user distribution p_u(y | x, c, r):
{user_summary}

Run priority score {priority_metric_name}:
{priority_score_text}

Agent run:
{agent_run_text}

Task:
Craft a labeling request that helps the user quickly adjudicate this run.

Other fields:
- title: concise and scannable.
- review_context: brief context and key events with citations.
- review_focus: a checklist of specific rubric-related questions to inspect; this field can be more detailed than review_context.
  Each review_focus item must include:
  - question: one focused rubric-related question with citation(s)
  - sample_answers: 1-3 plausible answer options the user can pick from

Scope requirement:
- Stay anchored to rubric r and its output schema.
- Ask only for judgments that map directly to rubric criteria/fields.
- Do not introduce new evaluation dimensions or preferences outside rubric r.

Return JSON:
{{
  "title": "<short title>",
  "review_context": "<succinct context and key events with citations>",
  "review_focus": [
    {{
      "question": "<specific rubric-related question with citation>",
      "sample_answers": [
        "<plausible answer option 1>",
        "<plausible answer option 2>",
        "<plausible answer option 3>"
      ]
    }}
  ]
}}
"""


def parse_labeling_request_payload(
    parsed: dict[str, Any],
    agent_run_id: str,
    context: LLMContext,
    user_distribution: OutputDistribution | None = None,
    user_distribution_reasoning: str | None = None,
) -> LabelingRequest:
    """Parse one labeling-request payload into a structured labeling request."""
    raw_title = parsed.get("title")
    raw_review_context = parsed.get("review_context")

    title = raw_title if isinstance(raw_title, str) else "Label this run"
    review_context_text = raw_review_context if isinstance(raw_review_context, str) else ""

    review_context, review_context_citations = resolve_citations_with_context(
        review_context_text, context, validate_text_ranges=True
    )

    review_focus_items: list[LabelingRequestFocusItem] = []
    raw_focus_raw = parsed.get("review_focus")
    raw_focus: list[object] = []
    if isinstance(raw_focus_raw, list):
        for focus_item in cast(list[object], raw_focus_raw):
            raw_focus.append(focus_item)

    for focus_item_raw in raw_focus:
        focus_item = cast(dict[str, Any], focus_item_raw)
        question_raw = focus_item.get("question")
        if not isinstance(question_raw, str):
            continue
        question_text, question_citations = resolve_citations_with_context(
            question_raw, context, validate_text_ranges=True
        )
        sample_answers = normalize_sample_answers(focus_item.get("sample_answers"))
        review_focus_items.append(
            LabelingRequestFocusItem(
                question=question_text,
                citations=question_citations,
                sample_answers=sample_answers,
            )
        )

    return LabelingRequest(
        agent_run_id=agent_run_id,
        title=title,
        review_context=review_context,
        review_context_citations=review_context_citations,
        review_focus=review_focus_items,
        user_distribution=user_distribution,
        user_distribution_reasoning=user_distribution_reasoning,
    )


async def generate_labeling_requests(
    agent_runs: list[AgentRun],
    estimates: list[RunDistributionEstimate],
    rubric: Rubric,
    user_context_text: str,
    llm_svc: BaseLLMService,
    max_requests: int | None = None,
    priority_scores_by_run_id: dict[str, float] | None = None,
    priority_metric_name: str = "H[p_u]",
) -> list[LabelingRequest]:
    """Generate user-facing labeling requests for high-priority runs."""
    assert_agreement_only_output_schema(rubric.output_schema)

    if not agent_runs or not estimates:
        return []

    runs_by_id = {run.id: run for run in agent_runs}
    viable_estimates = [
        estimate for estimate in estimates if estimate.user_distribution is not None
    ]
    if priority_scores_by_run_id is None:
        ranked_estimates = viable_estimates
    else:
        ranked_estimates = sorted(
            viable_estimates,
            key=lambda estimate: priority_scores_by_run_id.get(
                estimate.agent_run_id, float("-inf")
            ),
            reverse=True,
        )

    if max_requests is not None:
        ranked_estimates = ranked_estimates[:max_requests]

    prompts: list[list[dict[str, str]]] = []
    request_metadata: list[tuple[str, LLMContext, OutputDistribution, str | None]] = []
    for estimate in ranked_estimates:
        run = runs_by_id.get(estimate.agent_run_id)
        if run is None:
            continue
        user_distribution = estimate.user_distribution
        if user_distribution is None:
            continue
        context = LLMContext(items=[run])
        citation_instructions = context.get_system_message(
            interactive=False, include_citations=True
        )
        run_text = context.to_str()
        run_text, _, _ = truncate_to_token_limit(run_text, max_tokens=AGENT_RUN_TOK_LIMIT)

        priority_score = (
            priority_scores_by_run_id.get(estimate.agent_run_id)
            if priority_scores_by_run_id is not None
            else None
        )
        prompt = create_labeling_request_prompt(
            agent_run_text=run_text,
            citation_instructions=citation_instructions,
            rubric_text=rubric.rubric_text,
            rubric_output_schema=rubric.output_schema,
            user_context_text=user_context_text,
            user_distribution=user_distribution,
            user_distribution_reasoning=estimate.reasoning,
            priority_score=priority_score,
            priority_metric_name=priority_metric_name,
        )
        prompts.append([{"role": "user", "content": prompt}])
        request_metadata.append(
            (estimate.agent_run_id, context, user_distribution, estimate.reasoning)
        )

    if not prompts:
        return []

    outputs = await llm_svc.get_completions(
        inputs=prompts,
        model_options=[DEFAULT_MODEL_OPTION],
        max_new_tokens=8192,
        temperature=1.0,
        timeout=180.0,
    )

    results: list[LabelingRequest] = []
    for (agent_run_id, context, user_distribution, user_distribution_reasoning), output in zip(
        request_metadata, outputs
    ):
        if output.did_error:
            logger.warning(
                "LLM error while generating labeling request for run %s: %s",
                agent_run_id,
                "; ".join(str(e) for e in output.errors),
            )
            continue

        response_text = output.completions[0].text or ""
        parsed = parse_llm_json_response(
            response_text,
            keys=("title", "review_context", "review_focus"),
        )
        if parsed is None:
            logger.warning("Failed to parse labeling request JSON for run %s", agent_run_id)
            continue

        request = parse_labeling_request_payload(
            parsed=parsed,
            agent_run_id=agent_run_id,
            context=context,
            user_distribution=user_distribution,
            user_distribution_reasoning=user_distribution_reasoning,
        )
        results.append(request)

    return results


# === Misc ===


def parse_llm_json_response(response: str, keys: Sequence[str]) -> dict[str, Any] | None:
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass

    match = re.search(r"```json\s*(\{.*?\})\s*```", response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    for key in keys:
        escaped_key = re.escape(key)
        match = re.search(rf'\{{.*"{escaped_key}".*\}}', response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                continue

    return None


def _truncate_for_prompt(text: str, max_chars: int = 600) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


def _coerce_probability(value: Any) -> float | None:
    prob: float | None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        prob = float(value)
    elif isinstance(value, str):
        try:
            prob = float(value.strip())
        except ValueError:
            return None
    else:
        return None

    if not math.isfinite(prob) or prob < 0:
        return None
    return prob
