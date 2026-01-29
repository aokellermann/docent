from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, cast

from pydantic import BaseModel, Field

from docent._llm_util.llm_svc import BaseLLMService
from docent._llm_util.providers.preference_types import ModelOption
from docent._log_util.logger import get_logger
from docent.data_models.agent_run import AgentRun
from docent.data_models.citation import InlineCitation
from docent.judges.types import Rubric
from docent.sdk.llm_context import LLMContext, resolve_citations_with_context

if TYPE_CHECKING:
    from docent_core.docent.ai_tools.rubric.user_model import UserData

logger = get_logger(__name__)

# DEFAULT_MODEL_OPTION = ModelOption(
#     provider="openai",
#     model_name="gpt-5.2-2025-12-11",
#     reasoning_effort=None,
# )
DEFAULT_MODEL_OPTION = ModelOption(
    provider="anthropic",
    model_name="claude-opus-4-5-20251101",
    reasoning_effort=None,
)
# DEFAULT_MODEL_OPTION = ModelOption(
#     provider="anthropic",
#     model_name="claude-sonnet-4-5",
#     reasoning_effort=None,
# )
# DEFAULT_MODEL_OPTION = ModelOption(
#     provider="google",
#     model_name="gemini-3-flash-preview",
#     reasoning_effort=None,
# )


class SubRubricProposal(BaseModel):
    """A proposed sub-rubric extracted from the main rubric."""

    name: str  # Short descriptive name
    description: str  # What this sub-rubric measures
    key_indicators: list[str]  # Specific behaviors/patterns it captures


class DecompositionProposal(BaseModel):
    """A proposed decomposition of the current rubric into sub-rubrics."""

    summary: str  # Overview of why decomposition might help
    proposed_sub_rubrics: list[SubRubricProposal]
    recommendation: str  # Advice on whether to decompose
    confidence: str  # HIGH/MEDIUM/LOW


class ElicitedQuestionOption(BaseModel):
    title: str | None = None
    title_citations: list[InlineCitation] = Field(default_factory=list[InlineCitation])
    description: str | None = None
    description_citations: list[InlineCitation] = Field(default_factory=list[InlineCitation])


class ElicitedQuestion(BaseModel):
    agent_run_id: str | None = None
    quote_title: str | None = None
    framed_question: str | None = None
    framed_question_citations: list[InlineCitation] = Field(default_factory=list[InlineCitation])
    question_context: str | None = None
    question_context_citations: list[InlineCitation] = Field(default_factory=list[InlineCitation])
    example_options: list[ElicitedQuestionOption] = Field(
        default_factory=list[ElicitedQuestionOption]
    )
    error: str | None = None
    # Novelty rating assessed during extraction (HIGH/MEDIUM/LOW)
    novelty_rating: str | None = None
    novelty_rationale: str | None = None


class BottleneckExtractionInput(BaseModel):
    """Input for bottleneck extraction (decoupled from CLI-specific types)."""

    question_index: int
    agent_run_id: str | None
    original_question: str
    user_answer: str


class RubricChangeBottleneck(BaseModel):
    """Intermediate representation of extracted change info from a user answer."""

    question_index: int
    agent_run_id: str | None
    original_question: str
    user_answer: str
    change_type: str  # "add_criterion", "clarify_criterion", "add_exception", etc.
    affected_section: str | None
    key_insight: str
    proposed_change: str
    example_from_run: str | None
    confidence: str  # "high", "medium", "low"


class BottleneckExtractionResult(BaseModel):
    """Result of extracting a bottleneck from a single user answer."""

    question_index: int
    bottleneck: RubricChangeBottleneck | None
    error: str | None


class AggregatedRubricResult(BaseModel):
    """Result of aggregating bottlenecks into a final rubric update."""

    updated_rubric: Rubric
    change_summary: str
    bottlenecks_used: list[RubricChangeBottleneck]
    extracted_principles: list[str] | None = None
    error: str | None = None


def truncate_text(text: str, max_length: int = 150000) -> tuple[str, bool]:
    if len(text) <= max_length:
        return text, False

    truncated = text[:max_length]
    return truncated + f"\n\n[... TRUNCATED. Original length: {len(text)} chars]", True


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


def create_direct_question_prompt(
    agent_run_text: str,
    rubric_description: str,
    citation_instructions: str,
    max_questions: int = 3,
) -> str:
    """
    Create prompt for directly extracting questions from an agent run.

    This combines uncertainty identification and question framing into a single step,
    bypassing the aggregation process.

    Args:
        agent_run_text: Text representation of the agent run (with citation markers)
        rubric_description: Description of the rubric to evaluate against
        citation_instructions: Instructions for citing passages from the agent run
        max_questions: Maximum number of questions to extract per run (default: 3)

    Returns:
        Prompt string for the LLM
    """
    return f"""You are helping to refine a rubric for evaluating AI agent behavior by identifying cases where evaluators might disagree and framing them as clear questions.

{citation_instructions}

RUBRIC DESCRIPTION:
{rubric_description}

AGENT RUN TO ANALYZE:
{agent_run_text}

Your task: Identify decision-relevant ambiguities in the rubric—cases where two reasonable evaluators might genuinely disagree on how to score THIS PARTICULAR agent run—and frame each as a context + question pair.

QUALITY THRESHOLD - Only include a case if:
- Two reasonable, experienced evaluators could plausibly reach different scores
- The ambiguity is actually triggered by something specific in THIS run (not hypothetical)
- Resolving it would meaningfully change how this run should be judged

DO NOT include:
- Generic ambiguities that apply to any rubric (e.g., "what counts as 'good'?")
- Definitional nitpicks that wouldn't change practical judgment
- Hypothetical edge cases not actually present in this run
- Cases where the "right" interpretation is obvious from context

For each case (limit to {max_questions} most important, and it's completely fine to return fewer), provide:
1. A brief title capturing the essence of what this question is about
2. A standalone context summarizing the relevant situation
3. A succinct question asking for the user's judgment
4. Example answer options
5. A novelty rating and rationale

**FORMATTING GUIDANCE**:
- **Title**: A general description of the core ambiguity that could apply to other agent runs. No citations in titles.
- **Context**: Write a self-contained "case study" that someone can read and understand WITHOUT having seen the full agent run. Include specific details about what the agent did, the circumstances, and the outcome. Use citations [T0B5] to reference specific passages.
- **Question**: A SHORT, direct question asking for judgment. Assume the reader just read the context—don't repeat information. Examples:
  - "Should this count as a successful completion?"
  - "Is this response appropriately concise?"
  - "Does this meet the rubric's standard for error handling?"

Use bracket notation like [T0B5] or [T0B5:<RANGE>exact text<RANGE>] to cite specific passages. Citations can appear in context and question.

**NOVELTY RATING CRITERIA**:
Rate each question's novelty relative to the rubric:
- **HIGH**: Addresses something completely unrelated to the specific provisions made in the current rubric (a blind spot the rubric author didn't foresee)
- **MEDIUM**: Related to something already stated but potentially asks about a new dimension or related clarification
- **LOW**: Addresses something that is fairly unambiguously resolved given the rubric

Output your response as a JSON object:
{{
    "questions": [
        {{
            "title": "A general description of the core ambiguity",
            "context": "A standalone summary of the situation. Include what the agent was asked to do, what it actually did, and the outcome. Use citations. This should be readable as a complete 'case study' without needing the full agent run.",
            "question": "A short question asking for the user's judgment (one sentence).",
            "example_options": [
                {{
                    "title": "Option title",
                    "description": "What this option means"
                }}
            ],
            "novelty_rating": "HIGH|MEDIUM|LOW",
            "novelty_rationale": "Brief explanation of why this rating was assigned"
        }}
    ]
}}

Focus on quality over quantity. Return an empty list if the rubric is sufficiently clear for judging this run.

**IMPORTANT**: Do NOT invent ambiguities or grasp for marginal edge cases. If the rubric clearly covers this run, return an empty list. Only surface genuine ambiguities where reasonable evaluators would actually disagree—not hypothetical disagreements that are unlikely in practice.
"""


def create_question_deduplication_prompt(
    questions: list[ElicitedQuestion],
    rubric_description: str,
    max_questions: int,
    max_context_length: int = 500,
) -> str:
    """
    Create prompt for deduplicating and selecting the most diverse/interesting questions.

    Args:
        questions: List of ElicitedQuestion objects to deduplicate
        rubric_description: The rubric text to evaluate novelty against
        max_questions: Maximum number of questions to select (hard limit, not a target)
        max_context_length: Maximum characters of context to include per question

    Returns:
        Prompt string for the LLM
    """
    question_entries: list[str] = []
    has_pre_assessed_novelty = False

    for i, q in enumerate(questions):
        if q.error:
            continue

        q_id = f"Q{i:03d}"
        framed_question = q.framed_question or "N/A"
        context = q.question_context or ""
        if len(context) > max_context_length:
            context = context[:max_context_length] + "..."

        entry = f"""
--- {q_id} ---
Agent Run ID: {q.agent_run_id}
Context: {context}
Question: {framed_question}"""

        # Include pre-assessed novelty rating if available
        if q.novelty_rating:
            has_pre_assessed_novelty = True
            entry += f"\nPre-assessed Novelty: {q.novelty_rating}"
            if q.novelty_rationale:
                entry += f"\nRationale: {q.novelty_rationale}"

        entry += "\n"
        question_entries.append(entry)

    questions_str = "\n".join(question_entries)

    # Add note about pre-assessed ratings if any questions have them
    pre_assessed_note = ""
    if has_pre_assessed_novelty:
        pre_assessed_note = """
**Note on Pre-assessed Novelty**: Questions have pre-assessed novelty ratings (HIGH/MEDIUM/LOW) from the extraction step. Use these ratings as-is for prioritization—they indicate how much the question addresses a blind spot vs. something already covered in the rubric.
"""

    return f"""You are selecting questions to ask a user to clarify their rubric for evaluating AI agents.

CURRENT RUBRIC:
{rubric_description}

Below are {len(question_entries)} candidate questions extracted from agent run analysis. Each question has a pre-assessed novelty rating (HIGH/MEDIUM/LOW) indicating how much it addresses a blind spot vs. something already covered in the rubric.
{pre_assessed_note}
CANDIDATE QUESTIONS:
{questions_str}

## Your Task

Select a set of questions that is **MECE** (Mutually Exclusive, Collectively Exhaustive):

### 1. Mutually Exclusive (Deduplication)

**No two selected questions should address the same underlying ambiguity.**

- If multiple questions ask about the same issue (even if framed differently), select only the single best representative
- Questions are duplicates if resolving one would effectively resolve the other
- Err on the side of fewer, distinct questions over more overlapping ones

### 2. Collectively Exhaustive (Coverage)

**Don't omit high-value questions that address distinct rubric gaps.**

- Ensure the selected set covers the range of distinct ambiguities identified
- Prefer breadth (covering different aspects of the rubric) over depth (multiple questions about one aspect)
- HIGH novelty questions addressing blind spots should generally be included unless they duplicate another selected question

### 3. Prioritization

When choosing between non-duplicate questions:

1. **Novelty**: Prefer HIGH > MEDIUM > LOW (use the pre-assessed ratings)
2. **Impact**: Among same-novelty questions, prefer those where different answers would meaningfully change how runs are scored

## Constraints

**Maximum questions: {max_questions}**

This is a hard ceiling, not a target. Return fewer questions if:
- There aren't {max_questions} distinct ambiguities
- Lower-priority questions would be duplicative or low-impact
- The rubric is already clear on most points

It is completely acceptable—even expected—to return significantly fewer than {max_questions} questions.

## Output Format

Output as JSON:
{{
    "selected_questions": [
        {{
            "question_id": "Q003",
            "selection_rationale": "Brief explanation of why this was selected and what distinct ambiguity it addresses"
        }}
    ]
}}
"""


def create_bottleneck_extraction_prompt(
    rubric_text: str,
    agent_run_text: str,
    question: str,
    user_answer: str,
) -> str:
    """Create prompt for extracting a rubric change bottleneck from a user answer."""
    return f"""You are helping to refine a rubric for evaluating AI agent behavior based on user feedback.

CURRENT RUBRIC:
{rubric_text}

AGENT RUN CONTEXT (the run that prompted this question):
{agent_run_text}

QUESTION THAT WAS ASKED:
{question}

USER'S ANSWER:
{user_answer}

Your task: Extract a structured representation of how this answer should inform rubric changes.

Analyze the user's answer and determine:
1. What type of change is needed (add_criterion, clarify_criterion, add_exception, modify_scoring, etc.)
2. What section of the rubric is affected (if identifiable)
3. The key insight revealed by the user's answer
4. A specific proposed change to the rubric language/logic
5. Any example from the agent run that illustrates this
6. Your confidence in this interpretation (high, medium, low)

Output as JSON:
{{
    "change_type": "add_criterion|clarify_criterion|add_exception|modify_scoring|no_change",
    "affected_section": "section name or null if unclear",
    "key_insight": "What the user's answer reveals about how the rubric should handle this case",
    "proposed_change": "Specific language or logic to add/modify in the rubric",
    "example_from_run": "A concrete example from the agent run that illustrates this, or null",
    "confidence": "high|medium|low"
}}

If the user's answer doesn't suggest any rubric changes (e.g., they think the current rubric is fine), use change_type="no_change".
"""


def create_aggregation_prompt(
    rubric_text: str,
    output_schema: dict[str, Any],
    bottlenecks: list[RubricChangeBottleneck],
) -> str:
    """Create prompt for aggregating bottlenecks into a rubric update."""
    bottleneck_entries: list[str] = []
    for i, b in enumerate(bottlenecks, 1):
        entry = f"""
--- Example {i} ---
Scenario: {b.original_question}
User's Judgment: {b.user_answer}
Classification: {b.change_type}
Confidence: {b.confidence}
Context from Agent Run: {b.example_from_run or "N/A"}
"""
        bottleneck_entries.append(entry)

    bottlenecks_str = "\n".join(bottleneck_entries)
    schema_str = json.dumps(output_schema, indent=2)

    return f"""You are refining a rubric for evaluating AI agent behavior based on labeled examples from users.

CURRENT RUBRIC TEXT:
{rubric_text}

CURRENT OUTPUT SCHEMA:
{schema_str}

LABELED EXAMPLES FROM USER FEEDBACK:
{bottlenecks_str}

## Your Task

The examples above are **labeled data points** - they show how a user classified specific cases. Your job is to update the rubric so it can correctly classify:
1. The examples shown above (these are known positives/negatives)
2. **Other cases that are similar in spirit but not identical** (the examples do NOT exhaustively define the boundary)

## Critical Instructions

**DO NOT** create a rubric that simply lists the examples as special cases. This overfits.

**DO** identify the underlying principle that explains the user's judgments, then write criteria that capture that principle.

Think of this like supervised learning:
- The examples are your training data
- The rubric is your model
- A good model generalizes; a bad model memorizes

## Critical: Provisional Nature of Findings

These examples represent LIMITED feedback from a small sample of agent runs. The user's judgments are illustrative examples, NOT exhaustive rules. You MUST:

1. **Keep the core rubric unchanged** - Do not modify the original rubric criteria based on limited examples

2. **Add an "Exploratory Guidance" section** - All findings from user feedback go in a SEPARATE section at the end, clearly marked as provisional

3. **Use appropriate hedging** - Phrases like "Based on limited feedback...", "Examples suggest...", "Cases such as X may indicate..."

4. **Avoid closed-world assumptions** - Never imply the examples exhaustively define what's acceptable. The examples are merely data points, not boundaries.

5. **Preserve optionality** - A future judge using this rubric should understand these are suggestions that may need revision with more data

## Process

1. **Extract Principles**: For each example, ask "Why did the user classify this case this way? What general property makes it positive/negative?"

2. **Find Commonalities**: Look for patterns across examples. What unifying criteria would correctly classify all of them?

3. **Write Generalizable Criteria**: Update the rubric with criteria that:
   - Are stated in terms of PROPERTIES, not specific instances
   - Could correctly classify novel cases the user hasn't seen
   - Acknowledge that the listed examples are illustrative, not exhaustive

4. **Include a Coverage Note**: If you add examples to the rubric, explicitly state they are representative samples, e.g.:
   - "Examples of [positive/negative] cases include X, Y, Z. These are illustrative; similar cases should be evaluated by the same underlying principle."

## Output Format

<principles>
List the 1-3 underlying principles you extracted from the user's examples.
</principles>

<rubric_text>
The complete updated rubric text with the following structure:

[ORIGINAL RUBRIC TEXT - preserved unchanged or with minimal clarifications only]

---

## Exploratory Guidance (Based on Limited User Feedback)

**Note:** The following guidance is derived from a small sample of user feedback on specific agent runs. These are illustrative examples and suggestions, not definitive rules. This guidance may need revision as more feedback is collected.

[Tentative findings and suggestions go here, with appropriate hedging language like "Based on limited feedback...", "Examples suggest...", etc.]
</rubric_text>

<rubric_output_schema>
If the output schema needs changes, provide the updated JSON schema. Otherwise, output the exact original schema unchanged.
</rubric_output_schema>

<change_summary>
A brief summary (2-5 sentences) of what principles were extracted and how the rubric was updated to capture them.
</change_summary>
"""


def create_user_model_update_prompt(
    user_data: "UserData",
    current_model_text: str,
) -> str:
    """Create prompt for updating the user model based on collected feedback."""
    # Format QA pairs
    qa_entries: list[str] = []
    for i, qa in enumerate(user_data.qa_pairs, 1):
        entry = f"""
--- Feedback {i} ---
Question Context: {qa.question_context or "N/A"}
Question: {qa.question}
User's Answer: {qa.answer}
Custom Response: {"Yes" if qa.is_custom_response else "No"}
"""
        qa_entries.append(entry)

    qa_section = "\n".join(qa_entries) if qa_entries else "No feedback collected yet."

    return f"""You are synthesizing a user's intent and preferences for evaluating AI agent behavior.

INITIAL RUBRIC (what the user started with):
{user_data.initial_rubric}

CURRENT USER MODEL (your previous understanding):
{current_model_text}

COLLECTED FEEDBACK (questions the user answered):
{qa_section}

Your task: Update the user model to reflect what you've learned from this feedback.

The user model should capture:
1. **Core Intent**: What the user fundamentally cares about measuring
2. **Interpretation Preferences**: How they resolve ambiguous cases - cite specific examples from the question contexts
3. **Priorities**: What matters more vs less, with concrete illustrations from the feedback
4. **Grounded Examples**: Include 2-3 specific cases from the feedback that best illustrate the user's preferences

IMPORTANT: Ground every insight in SPECIFIC details from the question contexts above.
- Quote or reference actual agent behaviors that informed the user's judgments
- Avoid abstract generalizations - each principle should be anchored to actual data
- If describing a pattern, cite at least one concrete case that exemplifies it
- When the question context includes agent actions or outputs, reference those specifics

Write an updated user model as markdown. Be concise but comprehensive.
Focus on ACTIONABLE insights that would help a judge understand how this user thinks.

Output your response in this format:
<user_model>
[Your updated user model in markdown]
</user_model>
"""


async def update_user_model(
    user_data: "UserData",
    current_model_text: str,
    llm_svc: BaseLLMService,
) -> str:
    """
    Update the user model based on collected feedback.

    Args:
        user_data: The UserData containing initial rubric and QA pairs
        current_model_text: The current user model text
        llm_svc: LLM service for API calls

    Returns:
        Updated user model text (markdown string)
    """
    # Skip if no new QA pairs
    if not user_data.qa_pairs:
        return current_model_text

    prompt = create_user_model_update_prompt(user_data, current_model_text)

    outputs = await llm_svc.get_completions(
        inputs=[[{"role": "user", "content": prompt}]],
        model_options=[DEFAULT_MODEL_OPTION],
        max_new_tokens=4096,
        temperature=0.7,
        timeout=120.0,
    )

    output = outputs[0]

    if output.did_error:
        logger.warning(f"Failed to update user model: {output.errors}")
        return current_model_text

    llm_response = output.completions[0].text or ""

    # Parse user_model tag
    match = re.search(r"<user_model>(.*?)</user_model>", llm_response, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Fallback: return the whole response if no tags
    return llm_response.strip() or current_model_text


def create_decomposition_analysis_prompt(
    user_data: "UserData",
    current_model_text: str,
    previous_proposal: DecompositionProposal | None = None,
    user_feedback: str | None = None,
) -> str:
    """Create prompt for analyzing potential rubric decomposition into sub-rubrics."""
    # Format QA pairs with context
    qa_entries: list[str] = []
    for i, qa in enumerate(user_data.qa_pairs, 1):
        entry = f"""
--- Feedback {i} ---
Agent Run ID: {qa.agent_run_id}
Question Context: {qa.question_context or "N/A"}
Question: {qa.question}
User's Answer: {qa.answer}
Custom Response: {"Yes" if qa.is_custom_response else "No"}
"""
        qa_entries.append(entry)

    qa_section = "\n".join(qa_entries) if qa_entries else "No feedback collected yet."
    n_qa_pairs = len(user_data.qa_pairs)

    prompt = f"""You are analyzing whether a rubric for evaluating AI agents should be split into multiple sub-rubrics.

INITIAL RUBRIC:
{user_data.initial_rubric}

CURRENT USER MODEL (after {n_qa_pairs} rounds of feedback):
{current_model_text}

COLLECTED FEEDBACK ({n_qa_pairs} QA pairs):
{qa_section}

## Your Task

Analyze whether the user's feedback reveals DISTINCT evaluation dimensions that would be better served by separate rubrics.

Look for evidence of:
1. **Conflated Concepts**: Does the user's feedback address fundamentally different concerns that happen to be lumped together?
2. **Tension in Priorities**: Do some answers suggest competing values that are hard to balance in a single rubric?
3. **Distinct Measurement Axes**: Are there behaviors that should be evaluated independently rather than as part of one score?

## Important Guidelines

- **Ground every observation in specific QA pairs**: Reference actual feedback, not hypotheticals
- **Always provide suggestions**: You MUST propose at least one sub-rubric decomposition, even if you believe the current rubric is already well-structured
- **Focus on practical utility**: Would separate rubrics actually help measurement?
- **Use confidence to indicate benefit**: Use HIGH confidence when decomposition would clearly improve measurement, MEDIUM when it would provide modest benefits, and LOW when the rubric is already fairly coherent but decomposition could still offer minor improvements

## Output Format

Output your response as a JSON object:
{{
    "summary": "1-2 sentence overview of your analysis and whether decomposition would help",
    "proposed_sub_rubrics": [
        {{
            "name": "Short descriptive name for this sub-rubric",
            "description": "What this sub-rubric would measure",
            "key_indicators": [
                "Specific behavior or pattern this sub-rubric would capture",
                "Another indicator"
            ]
        }}
    ],
    "recommendation": "Clear advice on whether to decompose this rubric, and why",
    "confidence": "HIGH|MEDIUM|LOW"
}}

You MUST always propose at least one sub-rubric. If the current rubric is coherent, propose the most reasonable decomposition anyway and explain in the recommendation that while the rubric is fairly well-structured, this decomposition could offer specific benefits.
"""

    # Add feedback section if previous proposal and user feedback are provided
    if previous_proposal and user_feedback:
        feedback_section = f"""

## Previous Proposal

You previously proposed the following decomposition:
{previous_proposal.model_dump_json(indent=2)}

## User Feedback

The user provided the following feedback on your proposal:
{user_feedback}

Please revise your decomposition based on this feedback. The user may be:
- Asking for different sub-rubric boundaries
- Requesting more/fewer sub-rubrics
- Pointing out that certain aspects were missed
- Clarifying their priorities
"""
        return prompt + feedback_section

    return prompt


async def analyze_rubric_decomposition(
    user_data: "UserData",
    current_model_text: str,
    llm_svc: BaseLLMService,
    previous_proposal: DecompositionProposal | None = None,
    user_feedback: str | None = None,
) -> DecompositionProposal | None:
    """
    Analyze whether the current rubric should be decomposed into sub-rubrics.

    This function examines the collected QA pairs and current user model to identify
    whether the user's feedback reveals distinct evaluation dimensions that would be
    better served by separate rubrics.

    Args:
        user_data: The UserData containing initial rubric and QA pairs
        current_model_text: The current user model text
        llm_svc: LLM service for API calls
        previous_proposal: Optional previous decomposition proposal for refinement
        user_feedback: Optional user feedback on the previous proposal

    Returns:
        DecompositionProposal if analysis succeeds, None on error
    """
    # Skip if no QA pairs
    if not user_data.qa_pairs:
        logger.info("Skipping decomposition analysis: no QA pairs collected")
        return None

    prompt = create_decomposition_analysis_prompt(
        user_data,
        current_model_text,
        previous_proposal=previous_proposal,
        user_feedback=user_feedback,
    )

    outputs = await llm_svc.get_completions(
        inputs=[[{"role": "user", "content": prompt}]],
        model_options=[DEFAULT_MODEL_OPTION],
        max_new_tokens=4096,
        temperature=0.7,
        timeout=120.0,
    )

    output = outputs[0]

    if output.did_error:
        logger.warning(f"Failed to analyze rubric decomposition: {output.errors}")
        return None

    llm_response = output.completions[0].text or ""

    # Parse JSON response
    parsed = parse_llm_json_response(llm_response, keys=("summary", "proposed_sub_rubrics"))

    if not parsed:
        logger.warning("Failed to parse decomposition analysis JSON response")
        return None

    try:
        # Parse sub-rubrics
        sub_rubrics: list[SubRubricProposal] = []
        raw_sub_rubrics: list[Any] = parsed.get("proposed_sub_rubrics", [])
        for sr in raw_sub_rubrics:
            if isinstance(sr, dict):
                sr_dict = cast(dict[str, Any], sr)
                sub_rubrics.append(
                    SubRubricProposal(
                        name=str(sr_dict.get("name", "")),
                        description=str(sr_dict.get("description", "")),
                        key_indicators=list(sr_dict.get("key_indicators", [])),
                    )
                )

        return DecompositionProposal(
            summary=parsed.get("summary", ""),
            proposed_sub_rubrics=sub_rubrics,
            recommendation=parsed.get("recommendation", ""),
            confidence=parsed.get("confidence", "LOW"),
        )
    except Exception as e:
        logger.warning(f"Failed to create DecompositionProposal: {e}")
        return None


async def extract_questions_from_agent_runs(
    agent_runs: list[AgentRun],
    rubric_description: str,
    llm_svc: BaseLLMService,
    max_questions_per_run: int = 3,
) -> list[ElicitedQuestion]:
    """
    Extract questions directly from individual agent runs, bypassing aggregation.

    This function combines uncertainty identification and question framing into a single
    step for each agent run. It's an alternative to the 3-step process (identify ->
    aggregate -> frame) that preserves more detail from individual runs.

    Args:
        agent_runs: List of agent runs to analyze
        rubric_description: Description of the rubric to evaluate against
        llm_svc: LLM service for making API calls
        max_questions_per_run: Maximum questions to extract per run (default: 3)

    Returns:
        Flat list of ElicitedQuestion objects from all runs
    """
    logger.info(
        f"Starting direct question extraction for {len(agent_runs)} agent runs "
        f"(max {max_questions_per_run} questions per run)"
    )

    inputs: list[list[dict[str, str]]] = []
    run_metadata: list[dict[str, Any]] = []

    for agent_run in agent_runs:
        context = LLMContext(items=[agent_run])
        citation_instructions = context.get_system_message(
            interactive=False, include_citations=True
        )

        agent_run_text = context.to_str()
        agent_run_text, was_truncated = truncate_text(agent_run_text)

        if was_truncated:
            logger.warning(f"Truncated agent run {agent_run.id} for direct extraction")

        prompt = create_direct_question_prompt(
            agent_run_text=agent_run_text,
            rubric_description=rubric_description,
            citation_instructions=citation_instructions,
            max_questions=max_questions_per_run,
        )

        inputs.append([{"role": "user", "content": prompt}])
        run_metadata.append(
            {
                "agent_run_id": agent_run.id,
                "agent_run": agent_run,
                "was_truncated": was_truncated,
            }
        )

    logger.info(f"Prepared {len(inputs)} prompts, sending to LLM for direct extraction")
    outputs = await llm_svc.get_completions(
        inputs=inputs,
        model_options=[DEFAULT_MODEL_OPTION],
        max_new_tokens=16384,
        temperature=1.0,
        timeout=180.0,
    )

    results: list[ElicitedQuestion] = []

    for output, metadata in zip(outputs, run_metadata):
        agent_run_id = metadata["agent_run_id"]
        agent_run = metadata["agent_run"]

        if output.did_error:
            error_msg = "; ".join(str(e) for e in output.errors)
            results.append(
                ElicitedQuestion(
                    agent_run_id=agent_run_id,
                    error=f"LLM error: {error_msg}",
                )
            )
            continue

        llm_response = output.completions[0].text
        parsed = parse_llm_json_response(
            llm_response or "", keys=("questions", "question", "ambiguity")
        )

        if not parsed or "questions" not in parsed:
            results.append(
                ElicitedQuestion(
                    agent_run_id=agent_run_id,
                    error="Failed to parse JSON response",
                )
            )
            continue

        questions = parsed["questions"]
        if not questions:
            # No ambiguities found for this run - this is fine
            logger.debug(f"No ambiguities found for agent run {agent_run_id}")
            continue

        # Process each question from this run
        context = LLMContext(items=[agent_run])

        for q in questions:
            if not isinstance(q, dict):
                continue

            q_dict = cast(dict[str, Any], q)

            # Extract title (plain string, no citations)
            raw_title = q_dict.get("title", "")
            quote_title = raw_title if isinstance(raw_title, str) else None

            # Resolve citations in question
            raw_question = q_dict.get("question", "")
            question_text = raw_question if isinstance(raw_question, str) else ""
            framed_question, framed_question_citations = resolve_citations_with_context(
                question_text, context, validate_text_ranges=True
            )

            # Resolve citations in context
            raw_context = q_dict.get("context", "")
            context_text = raw_context if isinstance(raw_context, str) else ""
            question_context, question_context_citations = resolve_citations_with_context(
                context_text, context, validate_text_ranges=True
            )

            # Process example options
            example_options: list[ElicitedQuestionOption] = []
            raw_options: list[Any] = q_dict.get("example_options", []) or []
            for option in raw_options:
                if not isinstance(option, dict):
                    continue
                option_dict = cast(dict[str, Any], option)
                raw_opt_title: Any = option_dict.get("title")
                raw_description: Any = option_dict.get("description")
                opt_title_text = raw_opt_title if isinstance(raw_opt_title, str) else ""
                description_text = raw_description if isinstance(raw_description, str) else ""

                title_cleaned, title_citations = resolve_citations_with_context(
                    opt_title_text, context, validate_text_ranges=True
                )
                description_cleaned, description_citations = resolve_citations_with_context(
                    description_text, context, validate_text_ranges=True
                )

                example_options.append(
                    ElicitedQuestionOption(
                        title=title_cleaned,
                        title_citations=title_citations,
                        description=description_cleaned,
                        description_citations=description_citations,
                    )
                )

            # Extract novelty rating and rationale
            raw_novelty_rating = q_dict.get("novelty_rating")
            novelty_rating = raw_novelty_rating if isinstance(raw_novelty_rating, str) else None
            raw_novelty_rationale = q_dict.get("novelty_rationale")
            novelty_rationale = (
                raw_novelty_rationale if isinstance(raw_novelty_rationale, str) else None
            )

            results.append(
                ElicitedQuestion(
                    agent_run_id=agent_run_id,
                    quote_title=quote_title,
                    framed_question=framed_question,
                    framed_question_citations=framed_question_citations,
                    question_context=question_context,
                    question_context_citations=question_context_citations,
                    example_options=example_options,
                    novelty_rating=novelty_rating,
                    novelty_rationale=novelty_rationale,
                )
            )

    successful = sum(1 for r in results if r.error is None)
    logger.info(
        f"Direct extraction complete: {successful} questions extracted "
        f"from {len(agent_runs)} runs ({len(results) - successful} errors)"
    )
    return results


def sort_questions_by_novelty(
    questions: list[ElicitedQuestion],
    max_questions: int | None = None,
) -> list[ElicitedQuestion]:
    """
    Sort questions by novelty rating (HIGH > MEDIUM > LOW > None).

    This utility enables pre-aggregation sorting so that if context window is exceeded,
    only the highest-novelty questions are included in the deduplication step.

    Args:
        questions: List of ElicitedQuestion objects to sort
        max_questions: Optional limit - if provided, truncate to this many questions

    Returns:
        Sorted (and optionally truncated) list of ElicitedQuestion objects
    """
    novelty_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, None: 3}

    sorted_questions = sorted(
        questions,
        key=lambda q: (novelty_order.get(q.novelty_rating, 3), q.agent_run_id or ""),
    )

    if max_questions is not None:
        return sorted_questions[:max_questions]
    return sorted_questions


async def deduplicate_and_select_questions(
    questions: list[ElicitedQuestion],
    llm_svc: BaseLLMService,
    rubric_description: str,
    max_questions: int,
) -> tuple[list[ElicitedQuestion], dict[str, Any]]:
    """
    Deduplicate and select the most diverse/interesting questions from a list.

    This function takes all extracted questions and uses an LLM to select the most
    valuable questions based on novelty (relative to the rubric), impact,
    concreteness, diversity, and coverage criteria.

    Args:
        questions: List of ElicitedQuestion objects to deduplicate
        llm_svc: LLM service for making API calls
        rubric_description: The rubric text to evaluate novelty against
        max_questions: Maximum number of questions to select.
            This is a hard upper limit, not a target - the LLM may return fewer
            based on quality (prioritizing HIGH novelty questions).

    Returns:
        Tuple of:
        - Filtered list of ElicitedQuestion objects (selected questions)
        - Metadata dict with keys:
            - selected_ids: list of question IDs that were selected
            - rationales: dict mapping question_id to selection_rationale
            - error: error message if any, None otherwise

    Edge cases handled:
    - Empty input → returns empty list with appropriate metadata
    - All questions have errors → returns empty list
    - Fewer valid questions than max_questions → returns all valid questions (no LLM call)
    - LLM error → fallback to first max_questions valid questions
    - JSON parse failure → fallback to first max_questions valid questions
    """
    logger.info(
        f"Starting question deduplication: {len(questions)} input questions, "
        f"max_questions={max_questions}"
    )

    # Initialize metadata
    metadata: dict[str, Any] = {
        "selected_ids": [],
        "rationales": {},
        "error": None,
    }

    # Edge case: empty input
    if not questions:
        logger.info("No questions to deduplicate")
        return [], metadata

    # Filter out questions with errors
    valid_questions = [q for q in questions if q.error is None]
    logger.info(f"Valid questions (no errors): {len(valid_questions)}/{len(questions)}")

    # Edge case: all questions have errors
    if not valid_questions:
        logger.info("All questions have errors, returning empty list")
        metadata["error"] = "All input questions had errors"
        return [], metadata

    # Edge case: fewer valid questions than max_questions - return all valid questions
    if len(valid_questions) <= max_questions:
        logger.info(
            f"Only {len(valid_questions)} valid questions, returning all (no deduplication needed)"
        )
        # Build metadata for this case
        for i, q in enumerate(questions):
            if q.error is None:
                q_id = f"Q{i:03d}"
                metadata["selected_ids"].append(q_id)
                metadata["rationales"][q_id] = "Selected (fewer candidates than max_questions)"
        return valid_questions, metadata

    # Create prompt and call LLM
    prompt = create_question_deduplication_prompt(
        questions, rubric_description=rubric_description, max_questions=max_questions
    )

    outputs = await llm_svc.get_completions(
        inputs=[[{"role": "user", "content": prompt}]],
        model_options=[DEFAULT_MODEL_OPTION],
        max_new_tokens=8192,
        temperature=1.0,
        timeout=180.0,
    )

    output = outputs[0]

    # Handle LLM error - fallback to first max_questions valid questions
    if output.did_error:
        error_msg = "; ".join(str(e) for e in output.errors)
        logger.warning(
            f"LLM error during deduplication, falling back to first {max_questions}: {error_msg}"
        )
        metadata["error"] = f"LLM error (fallback used): {error_msg}"

        # Fallback: return first max_questions valid questions
        fallback_questions = valid_questions[:max_questions]
        for i, q in enumerate(questions):
            if q.error is None and q in fallback_questions:
                q_id = f"Q{i:03d}"
                metadata["selected_ids"].append(q_id)
                metadata["rationales"][q_id] = "Fallback selection (LLM error)"

        return fallback_questions, metadata

    # Parse LLM response
    llm_response = output.completions[0].text
    parsed = parse_llm_json_response(llm_response or "", keys=("selected_questions",))

    # Handle JSON parse failure - fallback to first max_questions valid questions
    if not parsed or "selected_questions" not in parsed:
        logger.warning(
            f"Failed to parse deduplication response, falling back to first {max_questions}"
        )
        metadata["error"] = "JSON parse error (fallback used)"

        # Fallback: return first max_questions valid questions
        fallback_questions = valid_questions[:max_questions]
        for i, q in enumerate(questions):
            if q.error is None and q in fallback_questions:
                q_id = f"Q{i:03d}"
                metadata["selected_ids"].append(q_id)
                metadata["rationales"][q_id] = "Fallback selection (JSON parse error)"

        return fallback_questions, metadata

    # Process successful response
    selected_questions_data = parsed["selected_questions"]

    # Build index mapping from Q### IDs to question indices
    selected_indices: list[int] = []
    for item in selected_questions_data:
        q_id = item.get("question_id", "")
        if q_id.startswith("Q") and q_id[1:].isdigit():
            idx = int(q_id[1:])
            if 0 <= idx < len(questions) and questions[idx].error is None:
                selected_indices.append(idx)
                metadata["selected_ids"].append(q_id)
                metadata["rationales"][q_id] = item.get("selection_rationale", "")

    # Build the result list preserving order from LLM
    selected_questions = [questions[idx] for idx in selected_indices]

    logger.info(
        f"Deduplication complete: selected {len(selected_questions)} questions from {len(valid_questions)} valid candidates"
    )

    return selected_questions, metadata


async def extract_bottleneck(
    input: BottleneckExtractionInput,
    agent_runs: list[AgentRun],
    rubric: Rubric,
    llm_svc: BaseLLMService,
) -> BottleneckExtractionResult:
    """
    Extract a rubric change bottleneck from a single user answer.

    Args:
        input: The extraction input containing question and answer info
        agent_runs: All sampled agent runs (for lookup)
        rubric: The base rubric
        llm_svc: LLM service

    Returns:
        BottleneckExtractionResult with either bottleneck or error
    """
    agent_run_id = input.agent_run_id

    # Find the agent run for context
    agent_run_text = "[Agent run not available]"
    if agent_run_id:
        for run in agent_runs:
            if run.id == agent_run_id:
                context = LLMContext(items=[run])
                agent_run_text = context.to_str()
                # Truncate if too long
                if len(agent_run_text) > 50000:
                    agent_run_text = agent_run_text[:50000] + "\n\n[... TRUNCATED]"
                break

    prompt = create_bottleneck_extraction_prompt(
        rubric_text=rubric.rubric_text,
        agent_run_text=agent_run_text,
        question=input.original_question,
        user_answer=input.user_answer,
    )

    outputs = await llm_svc.get_completions(
        inputs=[[{"role": "user", "content": prompt}]],
        model_options=[DEFAULT_MODEL_OPTION],
        max_new_tokens=4096,
        temperature=0.7,
        timeout=120.0,
    )

    output = outputs[0]

    if output.did_error:
        error_msg = "; ".join(str(e) for e in output.errors)
        return BottleneckExtractionResult(
            question_index=input.question_index,
            bottleneck=None,
            error=f"LLM error: {error_msg}",
        )

    llm_response = output.completions[0].text
    parsed = parse_llm_json_response(
        llm_response or "",
        keys=("change_type", "key_insight", "proposed_change"),
    )

    if not parsed:
        return BottleneckExtractionResult(
            question_index=input.question_index,
            bottleneck=None,
            error="Failed to parse JSON response",
        )

    try:
        bottleneck = RubricChangeBottleneck(
            question_index=input.question_index,
            agent_run_id=agent_run_id,
            original_question=input.original_question,
            user_answer=input.user_answer,
            change_type=parsed.get("change_type", "unknown"),
            affected_section=parsed.get("affected_section"),
            key_insight=parsed.get("key_insight", ""),
            proposed_change=parsed.get("proposed_change", ""),
            example_from_run=parsed.get("example_from_run"),
            confidence=parsed.get("confidence", "medium"),
        )
        return BottleneckExtractionResult(
            question_index=input.question_index,
            bottleneck=bottleneck,
            error=None,
        )
    except Exception as e:
        return BottleneckExtractionResult(
            question_index=input.question_index,
            bottleneck=None,
            error=f"Failed to create bottleneck: {e}",
        )


async def extract_all_bottlenecks(
    inputs: list[BottleneckExtractionInput],
    agent_runs: list[AgentRun],
    rubric: Rubric,
    llm_svc: BaseLLMService,
) -> list[BottleneckExtractionResult]:
    """
    Extract bottlenecks from all inputs in parallel.

    Args:
        inputs: List of extraction inputs
        agent_runs: All sampled agent runs
        rubric: The base rubric
        llm_svc: LLM service

    Returns:
        List of BottleneckExtractionResult
    """
    logger.info(f"Extracting bottlenecks from {len(inputs)} input(s)...")

    tasks = [extract_bottleneck(input, agent_runs, rubric, llm_svc) for input in inputs]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Process results
    extraction_results: list[BottleneckExtractionResult] = []
    for i, result in enumerate(results):
        if isinstance(result, BaseException):
            extraction_results.append(
                BottleneckExtractionResult(
                    question_index=inputs[i].question_index,
                    bottleneck=None,
                    error=f"Exception: {result}",
                )
            )
        else:
            # result is BottleneckExtractionResult
            extraction_results.append(result)

    num_success = sum(1 for r in extraction_results if r.bottleneck is not None)
    num_errors = sum(1 for r in extraction_results if r.error is not None)
    logger.info(f"Extracted {num_success} bottleneck(s), {num_errors} error(s)")

    return extraction_results


async def aggregate_bottlenecks_into_rubric(
    bottleneck_results: list[BottleneckExtractionResult],
    rubric: Rubric,
    llm_svc: BaseLLMService,
) -> AggregatedRubricResult:
    """
    Aggregate all bottlenecks into a final rubric update.

    Args:
        bottleneck_results: Results from extract_all_bottlenecks
        rubric: The base rubric
        llm_svc: LLM service

    Returns:
        AggregatedRubricResult with updated rubric
    """
    logger.info("Aggregating bottlenecks into rubric update...")

    # Filter to successful bottlenecks
    valid_bottlenecks = [r.bottleneck for r in bottleneck_results if r.bottleneck is not None]

    if not valid_bottlenecks:
        return AggregatedRubricResult(
            updated_rubric=rubric,
            change_summary="No valid bottlenecks to aggregate - rubric unchanged.",
            bottlenecks_used=[],
            error="No valid bottlenecks available",
        )

    # Filter out "no_change" bottlenecks
    actionable_bottlenecks = [b for b in valid_bottlenecks if b.change_type != "no_change"]

    if not actionable_bottlenecks:
        return AggregatedRubricResult(
            updated_rubric=rubric,
            change_summary="All user answers indicated no changes needed - rubric unchanged.",
            bottlenecks_used=valid_bottlenecks,
            error=None,
        )

    prompt = create_aggregation_prompt(
        rubric_text=rubric.rubric_text,
        output_schema=rubric.output_schema,
        bottlenecks=actionable_bottlenecks,
    )

    outputs = await llm_svc.get_completions(
        inputs=[[{"role": "user", "content": prompt}]],
        model_options=[DEFAULT_MODEL_OPTION],
        max_new_tokens=16384,
        temperature=0.7,
        timeout=180.0,
    )

    output = outputs[0]

    if output.did_error:
        error_msg = "; ".join(str(e) for e in output.errors)
        return AggregatedRubricResult(
            updated_rubric=rubric,
            change_summary="",
            bottlenecks_used=actionable_bottlenecks,
            error=f"LLM error: {error_msg}",
        )

    llm_response = output.completions[0].text or ""

    # Parse XML tags
    rubric_match = re.search(r"<rubric_text>(.*?)</rubric_text>", llm_response, re.DOTALL)
    schema_match = re.search(
        r"<rubric_output_schema>(.*?)</rubric_output_schema>", llm_response, re.DOTALL
    )
    summary_match = re.search(r"<change_summary>(.*?)</change_summary>", llm_response, re.DOTALL)
    principles_match = re.search(r"<principles>(.*?)</principles>", llm_response, re.DOTALL)

    if not rubric_match:
        return AggregatedRubricResult(
            updated_rubric=rubric,
            change_summary="",
            bottlenecks_used=actionable_bottlenecks,
            error="Failed to parse rubric_text from response",
        )

    new_rubric_text = rubric_match.group(1).strip()
    change_summary = (
        summary_match.group(1).strip()
        if summary_match
        else "Rubric updated based on user feedback."
    )

    # Parse extracted principles
    extracted_principles: list[str] | None = None
    if principles_match:
        principles_text = principles_match.group(1).strip()
        # Split by newlines and filter empty lines, treating each line as a principle
        extracted_principles = [
            line.strip().lstrip("-•").strip()
            for line in principles_text.split("\n")
            if line.strip() and not line.strip().startswith("#")
        ]
        if not extracted_principles:
            extracted_principles = None

    # Parse output schema if provided
    new_output_schema = rubric.output_schema
    if schema_match:
        try:
            new_output_schema = json.loads(schema_match.group(1).strip())
        except json.JSONDecodeError:
            pass  # Keep original schema

    # Create new rubric with incremented version
    try:
        updated_rubric = Rubric(
            rubric_text=new_rubric_text,
            output_schema=new_output_schema,
            version=rubric.version + 1,
            # Preserve other settings
            n_rollouts_per_input=rubric.n_rollouts_per_input,
            judge_variant=rubric.judge_variant,
            prompt_templates=rubric.prompt_templates,
            judge_model=rubric.judge_model,
            output_parsing_mode=rubric.output_parsing_mode,
            response_xml_key=rubric.response_xml_key,
        )
    except Exception as e:
        return AggregatedRubricResult(
            updated_rubric=rubric,
            change_summary="",
            bottlenecks_used=actionable_bottlenecks,
            error=f"Failed to create updated rubric: {e}",
        )

    logger.info(f"Created updated rubric (version {updated_rubric.version})")
    if extracted_principles:
        logger.info(f"Extracted principles: {len(extracted_principles)}")

    return AggregatedRubricResult(
        updated_rubric=updated_rubric,
        change_summary=change_summary,
        bottlenecks_used=actionable_bottlenecks,
        extracted_principles=extracted_principles,
        error=None,
    )
