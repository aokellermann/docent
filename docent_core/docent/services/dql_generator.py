from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Literal, Mapping, Sequence

from sqlglot import exp

from docent._llm_util.providers.preference_types import ModelOption
from docent._log_util import get_logger
from docent.data_models.chat.message import AssistantMessage, SystemMessage, UserMessage
from docent_core.docent.db.contexts import ViewContext
from docent_core.docent.db.dql import (
    DQLExecutionError,
    DQLParseError,
    DQLRegistry,
    DQLValidationError,
    JsonFieldInfo,
    build_default_registry,
    parse_dql_query,
)
from docent_core.docent.services.dql import DQLQueryResult, DQLService
from docent_core.docent.services.llms import PROVIDER_PREFERENCES, LLMService

logger = get_logger(__name__)

MAX_SCHEMA_COLUMNS = 60
MAX_EXPLORATION_RETRIES = 2
MAX_QUERY_RETRIES = 3


class DQLPhase(str, Enum):
    """Phase of the DQL generation workflow."""

    CLARIFICATION = "clarification"
    EXPLORATION = "exploration"
    QUERY = "query"


@dataclass(frozen=True)
class DQLGeneratorMessage:
    """A message in the DQL generation conversation."""

    role: Literal["user", "assistant", "system"]
    content: str
    query: str | None = None


@dataclass(frozen=True)
class RubricSchemaInfo:
    """Schema information for a rubric's output structure."""

    id: str
    version: int
    name: str | None
    output_fields: list[str]


@dataclass(frozen=True)
class DQLExplorationResult:
    """Result from an exploratory query."""

    query: str
    columns: tuple[str, ...]
    sample_rows: tuple[tuple[Any, ...], ...]
    error: str | None = None


@dataclass(frozen=True)
class DQLGenerationOutcome:
    """Result of a DQL generation request."""

    query: str
    assistant_message: str
    execution_result: DQLQueryResult | None
    execution_error: str | None
    used_tables: list[str]
    # Phase fields
    phase: DQLPhase = DQLPhase.QUERY
    clarification_question: str | None = None
    exploration_results: tuple[DQLExplorationResult, ...] | None = None
    requires_user_response: bool = False


def _normalize_query(query: str) -> str:
    """Strip trailing semicolons and whitespace from a query."""
    cleaned = query.strip()
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1]
    return cleaned.strip()


def _clean_generated_query(text: str) -> str:
    """Clean up a model-generated query string while preserving formatting."""
    cleaned = _strip_ansi(text or "")
    # Normalize line endings to \n and remove trailing whitespace per line
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in cleaned.split("\n")]
    # Remove leading/trailing blank lines
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def _registry_columns_hint(registry: DQLRegistry) -> str:
    """Build a hint string listing available columns per table."""
    hints: list[str] = []
    for table in registry.iter_tables():
        cols = [c for c in sorted(table.allowed_columns) if c.lower() != "collection_id"]
        if cols:
            hints.append(f"{table.name}: {', '.join(cols)}")
    return "\n".join(hints)


def _prettify_base_query(
    query: str | None, registry: DQLRegistry, collection_id: str
) -> str | None:
    """Return the query with minimal normalization (no reformatting).

    Pretty-printing is disabled to preserve the user's original formatting,
    which allows the LLM to create clean, minimal diffs when editing queries.
    """
    # Unused but kept for potential future use
    _ = registry
    _ = collection_id
    if not query:
        return None
    return _normalize_query(query)


def _schema_summary(registry: DQLRegistry, max_columns: int = MAX_SCHEMA_COLUMNS) -> str:
    """Build a human-readable schema summary for the system prompt."""
    lines: list[str] = ["Tables you can use:"]
    for table in sorted(registry.iter_tables(), key=lambda tbl: tbl.name):
        alias_hint = f" (aliases: {', '.join(sorted(table.aliases))})" if table.aliases else ""
        lines.append(f"- {table.name}{alias_hint}")

        allowed_columns = sorted(
            col for col in table.allowed_columns if col.lower() != "collection_id"
        )
        shown_columns = allowed_columns[:max_columns]
        hidden_count = len(allowed_columns) - len(shown_columns)
        column_line = f"  columns: {', '.join(shown_columns)}"
        if hidden_count > 0:
            column_line += f" (+{hidden_count} more)"
        lines.append(column_line)

        if table.column_aliases:
            alias_pairs = [
                f"{alias} -> {target}" for alias, target in sorted(table.column_aliases.items())
            ]
            lines.append(f"  column aliases: {', '.join(alias_pairs)}")

        if table.json_field_paths:
            lines.append(f"  json fields: {', '.join(sorted(table.json_field_paths))}")
    return "\n".join(lines)


def _build_rubric_schema_summary(rubrics: Sequence[RubricSchemaInfo]) -> str:
    """Build a summary of rubric output schemas for the system prompt."""
    if not rubrics:
        return ""
    lines = ["", "RUBRIC OUTPUT SCHEMAS (use output->>'field' to access):"]
    for rubric in rubrics:
        name = rubric.name[:400] + "..." if rubric.name and len(rubric.name) > 400 else rubric.name
        fields_str = ", ".join(rubric.output_fields) if rubric.output_fields else "(no fields)"
        lines.append(f"- {rubric.id} (v{rubric.version}): {fields_str}")
        if name:
            lines.append(f"  Description: {name}")
    return "\n".join(lines)


def _build_system_prompt(
    schema_summary: str,
    current_query: str | None,
    available_tables: frozenset[str],
    rubric_schemas: Sequence[RubricSchemaInfo] | None = None,
    exploration_context: str | None = None,
) -> str:
    """Build the system prompt for the DQL generator.

    Args:
        schema_summary: Human-readable schema summary.
        current_query: Optional current query in the editor.
        available_tables: Set of table names available in the registry.
        rubric_schemas: Optional rubric output schema information.
        exploration_context: Optional results from exploration queries to inject.
    """
    prompt_lines = [
        "You write Docent Query Language (DQL) SELECT statements.",
        "",
        "CRITICAL: You can ONLY use tables and columns from the schema below. The schema lists ALL "
        "tables you have access to. Do NOT reference, mention, or suggest tables that are not in the "
        "schema - they do not exist. If a user asks about data that would require a table not in your "
        "schema, explain that you don't have access to that data.",
        "",
        "DQL allows a single read-only SELECT. Cast text/JSON fields to numeric when aggregating.",
        "Qualify columns when multiple tables appear.",
        "",
        "THREE-PHASE WORKFLOW:",
        "",
        "PHASE 1 - CLARIFICATION (when needed):",
        "- If the user's request is ambiguous or missing critical details, ask ONE focused clarifying question.",
        "- Do NOT generate SQL in this phase.",
        "- Examples of when to clarify:",
        "  - User references a column name that doesn't exist (ask which column they mean)",
        "  - User wants to filter by a value but hasn't specified which one",
        "  - Request is too vague to write a meaningful query",
        "",
        "PHASE 2 - EXPLORATION (when needed):",
        "- If you need to discover actual data values, available fields in JSONB columns, or verify assumptions, "
        "write exploration queries.",
        "- Exploration queries should be simple SELECTs with LIMIT to get sample values.",
        "- Run multiple exploration queries if needed to gather all context.",
        "",
        "PHASE 3 - QUERY WRITING:",
        "- Once you have clarity and any needed sample data, write the final query.",
        "- If you used exploration, reference those results to write accurate queries.",
        "",
        "DECISION LOGIC:",
        "1. First, check if you understand the request clearly. If not -> CLARIFICATION",
        "2. Next, check if you need to see actual data values. If yes -> EXPLORATION",
        "3. Otherwise -> QUERY",
        "",
        "OUTPUT FORMAT:",
        "Respond with JSON matching ONE of these formats:",
        "",
        'For CLARIFICATION: {"phase": "clarification", "clarification_question": "<your question>", '
        '"notes": "<brief context>"}',
        "",
        'For EXPLORATION: {"phase": "exploration", "exploration_queries": ["<query1>", "<query2>"], '
        '"notes": "<what you need to learn>"}',
        "",
        'For QUERY: {"phase": "query", "dql": "<final query>", "notes": "<explanation>"}',
        "",
        "IMPORTANT: Do NOT include collection_id in your queries. The backend automatically scopes "
        "all queries to the current collection - you never need to filter by collection_id.",
        "",
        "When the user asks for a specific row by name or other attribute (e.g., 'show me the run "
        "named foo'), first write a query to find that row's id, then use that id in subsequent "
        "queries. If you need to look something up, say so in your notes.",
        "",
        "PRESERVING FORMATTING:",
        "- When editing an existing query, preserve its whitespace and formatting style.",
        "- Only change the lines that need to be modified to fulfill the user's request.",
        "- Do NOT reformat or reorganize the query unless the user specifically asks for cleanup.",
        "- This creates clean, minimal diffs that are easy to review.",
    ]

    # Only include rubric/judge documentation if those tables are available
    if "rubrics" in available_tables or "judge_results" in available_tables:
        prompt_lines.extend(
            [
                "",
                "RUBRIC & JUDGE RESULTS:",
                "- Users may say 'judges' when they mean `rubrics`, or 'rubric_results' when they mean "
                "`judge_results`. Understand both, but always use the actual table names in your queries.",
                "- `rubrics` table defines evaluation criteria with composite PK (id, version).",
                "- `judge_results` stores evaluation outcomes. Join via agent_run_id and (rubric_id, rubric_version).",
                "- Always filter: result_type = 'DIRECT_RESULT' to exclude failed evaluations.",
                "- Results are in `output` JSONB column. Use the RUBRIC OUTPUT SCHEMAS below to see available fields.",
                "",
                "HANDLING MULTIPLE ROLLOUTS:",
                "- Rubrics may have multiple judge_results rows per agent_run (for reliability via repeated evaluation).",
                "- To get the consensus/mode value, use mode() WITHIN GROUP:",
                "  mode() WITHIN GROUP (ORDER BY jr.output->>'label') AS label",
                "- Example CTE pattern for getting modal results per rubric:",
                "  WITH rubric_abc123_modes AS (",
                "    SELECT",
                "      jr.agent_run_id,",
                "      mode() WITHIN GROUP (ORDER BY jr.output->>'label') AS label,",
                "      mode() WITHIN GROUP (ORDER BY jr.output->>'explanation') AS explanation",
                "    FROM judge_results jr",
                "    WHERE jr.rubric_id = 'abc123...' AND jr.rubric_version = 2",
                "      AND jr.result_type = 'DIRECT_RESULT'",
                "    GROUP BY jr.agent_run_id",
                "  )",
                "- For multiple rubrics, create separate CTEs and FULL OUTER JOIN on agent_run_id.",
                "",
                "RUBRIC VERSIONING:",
                "- When user doesn't specify version, use the latest. Query max version or ORDER BY version DESC LIMIT 1.",
            ]
        )

    # Only include labels documentation if the labels table is available
    if "labels" in available_tables:
        prompt_lines.extend(
            [
                "",
                "LABELS (distinct from rubrics):",
                "- `labels` table stores manual/human labels, joined via agent_run_id and filtered by label_set_id.",
                "- `label_value` is JSONB with fields like label_value->>'label', label_value->>'explanation'.",
            ]
        )

    prompt_lines.extend(
        [
            "",
            "DYNAMIC SCHEMA - DO NOT ASSUME STRUCTURE:",
            "- metadata_json, rubric output, and label_value structures vary per collection/rubric/label_set.",
            "- Check the RUBRIC OUTPUT SCHEMAS section below for available output fields per rubric.",
            "- If the schema doesn't show the fields you need, use EXPLORATION phase to inspect the data first.",
        ]
    )

    # Only include agent_runs documentation if that table is available
    if "agent_runs" in available_tables:
        prompt_lines.extend(
            [
                "",
                "DATA NOTES:",
                "- agent_runs: metadata_json contains run-level metadata (not rubric scores). Access nested fields "
                "with metadata_json->>'field' or metadata_json->'nested'->>'field'.",
            ]
        )

    # Only include tags documentation if that table is available
    if "tags" in available_tables:
        prompt_lines.append(
            "- tags: Use array_agg(t.value ORDER BY t.value) to collect tags for an agent_run."
        )

    prompt_lines.extend(
        [
            "",
            "NOTES GUIDELINES:",
            "- Format the notes field as markdown. Use `backticks` for column/table names.",
            "- If showing example SQL in notes, use ```sql code blocks.",
            "- Present yourself as the DQL expert. Focus notes on helping the user understand the query.",
            "- If the user points out an error, acknowledge it and explain the fix.",
            "- IMPORTANT: Your notes go directly to the user. The user does not see system retry messages.",
            "  Do NOT reference 'previous queries', 'fixing errors', 'corrections', or 'the error'",
            "  unless the user explicitly mentioned an error. Write notes as if this is your first response.",
            "- Never mention PostgreSQL or Postgres. Refer only to DQL.",
            "",
            "SCOPE & LIMITATIONS:",
            "- You can ONLY produce read-only DQL SELECT queries to analyze data in the current collection.",
            "- You CANNOT:",
            "  - Update, insert, or delete data",
            "  - Create or modify agent runs, rubrics, labels, or any other entities",
            "  - Access docent documentation or external resources",
            "  - Execute actions outside of data querying",
            "- When a user asks for something outside your scope:",
            "  1. Acknowledge their request politely",
            "  2. Briefly explain that you can only write DQL queries to analyze data",
            "  3. If a query could help with their underlying goal, suggest it. For example:",
            "     - 'Create a new rubric' → Offer to query existing rubrics to help them understand the structure",
            "     - 'Update run status' → Offer to query runs with specific statuses to help them identify what needs updating",
            "     - 'Show documentation' → Offer to explore the schema or sample data to help them understand available fields",
            "  4. Use the clarification phase to provide this helpful response",
            "",
            "Schema:",
            schema_summary,
        ]
    )

    # Add rubric output schemas if available
    if rubric_schemas:
        prompt_lines.append(_build_rubric_schema_summary(rubric_schemas))

    # Inject exploration results if present (from previous exploration queries)
    if exploration_context:
        prompt_lines.extend(
            [
                "",
                "EXPLORATION RESULTS (from queries you requested):",
                exploration_context,
                "",
                "Use these results to write an accurate query for the user's request.",
                "You MUST now respond with phase: 'query' and provide the final DQL.",
            ]
        )

    if current_query:
        prompt_lines.extend(
            [
                "",
                "Current working query (edit it when the user asks for changes):",
                current_query,
            ]
        )
    return "\n".join(prompt_lines)


def _strip_code_fence(text: str) -> str:
    """Remove markdown code fences from text."""
    fenced = text.strip()
    if fenced.startswith("```"):
        fenced = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", fenced, flags=re.DOTALL)
    return fenced.strip()


ANSI_PATTERN = re.compile(r"\x1B\[[0-9;]*[A-Za-z]")


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    return ANSI_PATTERN.sub("", text)


def _extract_string_list(value: object) -> list[str]:
    """Extract a list of strings from an unknown value, normalizing each."""
    if not isinstance(value, list):
        return []
    result: list[str] = []
    # Cast to list[object] to satisfy type checker
    items: list[object] = list(value)  # type: ignore[reportUnknownArgumentType]
    for item in items:
        if isinstance(item, str) and item.strip():
            result.append(_normalize_query(item))
    return result


def _extract_json_payload(raw_text: str) -> dict[str, object] | None:
    """Extract a JSON object from model output, handling code fences."""
    cleaned = _strip_code_fence(raw_text)
    try:
        payload: object = json.loads(cleaned)
        if isinstance(payload, dict):
            return payload  # type: ignore[reportReturnType]
    except Exception:
        pass

    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
        if isinstance(payload, dict):
            return payload  # type: ignore[reportReturnType]
    except Exception:
        return None
    return None


@dataclass
class ParsedPhaseResponse:
    """Parsed response from the LLM indicating which phase and relevant content."""

    phase: DQLPhase
    clarification_question: str | None = None
    exploration_queries: list[str] | None = None
    dql: str | None = None
    notes: str = ""


def _parse_phase_response(raw_text: str) -> ParsedPhaseResponse:
    """Parse LLM output to determine phase and extract relevant content."""
    payload = _extract_json_payload(raw_text)
    if not payload:
        # Fallback: assume query phase with extracted SELECT
        match = re.search(r"(?is)select\b.+", raw_text.strip())
        if match:
            return ParsedPhaseResponse(phase=DQLPhase.QUERY, dql=_normalize_query(match.group(0)))
        raise ValueError("Could not parse model response")

    # Determine phase from payload
    phase_str = str(payload.get("phase", "query")).lower()
    if phase_str == "clarification":
        phase = DQLPhase.CLARIFICATION
    elif phase_str == "exploration":
        phase = DQLPhase.EXPLORATION
    else:
        phase = DQLPhase.QUERY

    notes_value = payload.get("notes") or payload.get("reasoning") or ""
    notes = str(notes_value) if notes_value else ""

    if phase == DQLPhase.CLARIFICATION:
        question = payload.get("clarification_question")
        return ParsedPhaseResponse(
            phase=phase,
            clarification_question=str(question) if question else notes,
            notes=notes,
        )

    if phase == DQLPhase.EXPLORATION:
        queries_raw = payload.get("exploration_queries")
        queries = _extract_string_list(queries_raw)
        return ParsedPhaseResponse(
            phase=phase,
            exploration_queries=queries if queries else None,
            notes=notes,
        )

    # Query phase
    query_value = payload.get("dql") or payload.get("query")
    if isinstance(query_value, str) and query_value.strip():
        return ParsedPhaseResponse(
            phase=phase,
            dql=_normalize_query(query_value),
            notes=notes,
        )

    # Fallback: try to extract SELECT from notes or raw text
    match = re.search(r"(?is)select\b.+", raw_text.strip())
    if match:
        return ParsedPhaseResponse(
            phase=DQLPhase.QUERY, dql=_normalize_query(match.group(0)), notes=notes
        )

    raise ValueError("Model response did not include a DQL query.")


def _tables_from_expression(expression: exp.Expression) -> list[str]:
    """Extract table names referenced in a parsed expression."""
    names: set[str] = set()
    for table in expression.find_all(exp.Table):
        if table.name:
            names.add(str(table.name))
    return sorted(names)


def _strip_collection_filters(expression: exp.Expression) -> exp.Expression:
    """Remove predicates that reference collection_id to avoid redundant filters."""
    where_expr = expression.args.get("where")
    if where_expr is None:
        return expression

    def _has_collection_column(node: exp.Expression) -> bool:
        return any(
            col.name and col.name.lower() == "collection_id" for col in node.find_all(exp.Column)
        )

    if _has_collection_column(where_expr):
        expression = expression.copy()
        expression.set("where", None)
        return expression

    return expression


class DQLGeneratorService:
    """Service for generating DQL queries from natural language using LLMs."""

    def __init__(self, dql_svc: DQLService, llm_svc: LLMService):
        self.dql_svc = dql_svc
        self.llm_svc = llm_svc

    async def _call_llm(
        self,
        messages: list[UserMessage | AssistantMessage | SystemMessage],
        model_options: list[ModelOption],
    ) -> str:
        """Call the LLM and return raw text response."""
        outputs = await self.llm_svc.get_completions(
            inputs=[messages],
            model_options=model_options,
            max_new_tokens=10 * 1024,
            temperature=1.0,
            use_cache=True,
        )

        result = outputs[0]
        if result.did_error or result.first is None or not result.first.text:
            error_details: list[str] = []
            if result.did_error:
                error_details.append(f"errors={result.errors}")
            if result.first is None:
                error_details.append("no completions returned")
            elif not result.first.text:
                error_details.append("empty text in completion")
            logger.info("DQL generator empty model response: %s", ", ".join(error_details))
            raise ValueError("Model did not return a response")

        raw_text = result.first.text
        try:
            logger.info("DQL generator raw model response (truncated): %s", raw_text[:2000])
        except Exception:
            pass
        return raw_text

    async def _execute_exploration_query(
        self,
        ctx: ViewContext,
        query: str,
        registry: DQLRegistry,
    ) -> DQLExplorationResult:
        """Execute a single exploration query and return results."""
        if ctx.user is None:
            return DQLExplorationResult(
                query=query,
                columns=(),
                sample_rows=(),
                error="User context unavailable",
            )

        try:
            # Validate and execute the query
            parsed_expression = parse_dql_query(
                query, registry=registry, collection_id=ctx.collection_id
            )
            parsed_expression = _strip_collection_filters(parsed_expression)

            result = await self.dql_svc.execute_query(
                user=ctx.user,
                collection_id=ctx.collection_id,
                dql=query,
                max_rows=50,  # Limit exploration results
            )

            return DQLExplorationResult(
                query=query,
                columns=tuple(result.columns),
                sample_rows=tuple(tuple(row) for row in result.rows[:20]),
                error=None,
            )
        except (DQLParseError, DQLValidationError, DQLExecutionError, Exception) as exc:
            logger.info("Exploration query failed: %s - %s", query[:100], exc)
            return DQLExplorationResult(
                query=query,
                columns=(),
                sample_rows=(),
                error=str(exc),
            )

    def _format_exploration_results(self, results: Sequence[DQLExplorationResult]) -> str:
        """Format exploration results for injection into the system prompt."""
        lines: list[str] = []
        for i, result in enumerate(results, 1):
            lines.append(f"Query {i}: {result.query}")
            if result.error:
                lines.append(f"  Error: {result.error}")
            else:
                lines.append(f"  Columns: {', '.join(result.columns)}")
                if result.sample_rows:
                    lines.append("  Sample rows:")
                    for row in result.sample_rows[:10]:
                        row_str = " | ".join(str(v)[:50] for v in row)
                        lines.append(f"    {row_str}")
                else:
                    lines.append("  (no rows returned)")
            lines.append("")
        return "\n".join(lines)

    def _handle_clarification_phase(
        self,
        response: ParsedPhaseResponse,
    ) -> DQLGenerationOutcome:
        """Handle clarification phase - return question without executing anything."""
        question = response.clarification_question or response.notes or "Could you clarify?"
        return DQLGenerationOutcome(
            query="",
            assistant_message=question,
            execution_result=None,
            execution_error=None,
            used_tables=[],
            phase=DQLPhase.CLARIFICATION,
            clarification_question=question,
            requires_user_response=True,
        )

    async def _handle_exploration_phase(
        self,
        response: ParsedPhaseResponse,
        ctx: ViewContext,
        schema_summary: str,
        base_query: str | None,
        converted_messages: list[UserMessage | AssistantMessage | SystemMessage],
        registry: DQLRegistry,
        model_options: list[ModelOption],
        rubric_schemas: Sequence[RubricSchemaInfo] | None,
    ) -> DQLGenerationOutcome:
        """Handle exploration phase - run queries then proceed to query phase."""
        exploration_results: list[DQLExplorationResult] = []

        for query in response.exploration_queries or []:
            # Try each exploration query with retries
            result: DQLExplorationResult | None = None
            for attempt in range(MAX_EXPLORATION_RETRIES):
                result = await self._execute_exploration_query(ctx, query, registry)
                if result.error is None:
                    break
                logger.info(
                    "Exploration query retry %d/%d: %s",
                    attempt + 1,
                    MAX_EXPLORATION_RETRIES,
                    result.error,
                )
            if result:
                exploration_results.append(result)

        # Format exploration results for context injection
        exploration_context = self._format_exploration_results(exploration_results)

        # Rebuild prompt with exploration results
        available_tables = frozenset(t.name for t in registry.iter_tables())
        updated_prompt = _build_system_prompt(
            schema_summary,
            base_query,
            available_tables,
            rubric_schemas,
            exploration_context=exploration_context,
        )

        # Call LLM again for query phase with exploration context
        updated_messages: list[UserMessage | AssistantMessage | SystemMessage] = [
            SystemMessage(content=updated_prompt),
            *converted_messages[1:],  # Skip old system message
        ]

        try:
            raw_text = await self._call_llm(updated_messages, model_options)
            query_response = _parse_phase_response(raw_text)
        except Exception as exc:
            logger.info("Failed to get query after exploration: %s", exc)
            return DQLGenerationOutcome(
                query="",
                assistant_message=response.notes or "",
                execution_result=None,
                execution_error=f"Failed to generate query after exploration: {exc}",
                used_tables=[],
                phase=DQLPhase.EXPLORATION,
                exploration_results=tuple(exploration_results),
                requires_user_response=False,
            )

        # Now handle the query phase response
        return await self._handle_query_phase(
            query_response,
            ctx,
            schema_summary,
            base_query,
            updated_messages,
            registry,
            model_options,
            rubric_schemas,
            exploration_results=exploration_results,
        )

    async def _handle_query_phase(
        self,
        response: ParsedPhaseResponse,
        ctx: ViewContext,
        schema_summary: str,
        base_query: str | None,
        base_messages: list[UserMessage | AssistantMessage | SystemMessage],
        registry: DQLRegistry,
        model_options: list[ModelOption],
        rubric_schemas: Sequence[RubricSchemaInfo] | None,
        exploration_results: list[DQLExplorationResult] | None = None,
    ) -> DQLGenerationOutcome:
        """Handle query phase - execute query with retry logic."""
        if ctx.user is None:
            raise ValueError("User context is required to execute DQL.")

        allowed_hint = _registry_columns_hint(registry)
        final_query = ""
        execution_result: DQLQueryResult | None = None
        execution_error: str | None = None
        assistant_message = response.notes or ""
        used_tables: list[str] = []

        # Get initial query from response
        if response.dql:
            final_query = _clean_generated_query(response.dql)

        current_messages = base_messages

        # Retry loop for query execution
        for attempt in range(MAX_QUERY_RETRIES):
            if not final_query:
                execution_error = "No query was generated"
                break

            try:
                parsed_expression = parse_dql_query(
                    final_query,
                    registry=registry,
                    collection_id=ctx.collection_id,
                )
                parsed_expression = _strip_collection_filters(parsed_expression)
                used_tables = _tables_from_expression(parsed_expression)

                execution_result = await self.dql_svc.execute_query(
                    user=ctx.user,
                    collection_id=ctx.collection_id,
                    dql=final_query,
                )
                execution_error = None
                break  # Success
            except (DQLParseError, DQLValidationError, DQLExecutionError, Exception) as exc:
                execution_error = str(exc)
                logger.info(
                    "DQL auto-generator query failed (attempt %d): %s",
                    attempt + 1,
                    execution_error,
                )

            if attempt < MAX_QUERY_RETRIES - 1:
                # Build retry message
                retry_user_message = UserMessage(
                    content=(
                        "[SYSTEM RETRY - USER DOES NOT SEE THIS MESSAGE]\n"
                        f"Error: {execution_error}\n\n"
                        f"Failed query:\n{final_query or '<empty>'}\n\n"
                        "Use only columns from the schema. Avoid '*' and invalid columns. "
                        "Columns by table:\n"
                        f"{allowed_hint}\n\n"
                        'Return corrected DQL as JSON: {"phase": "query", "dql": "...", "notes": "..."}.\n\n'
                        "CRITICAL: In your 'notes', do NOT mention corrections, fixes, errors, "
                        "retries, or previous attempts. The user only sees your notes - they do not "
                        "know about this retry. Write your notes as a fresh response to the original request."
                    )
                )
                current_messages = [*current_messages, retry_user_message]

                try:
                    raw_text = await self._call_llm(current_messages, model_options)
                    retry_response = _parse_phase_response(raw_text)
                    if retry_response.dql:
                        final_query = _clean_generated_query(retry_response.dql)
                    if retry_response.notes:
                        assistant_message = retry_response.notes
                except Exception as retry_exc:
                    logger.info("Retry LLM call failed: %s", retry_exc)

        # When all retries are exhausted, modify the message to acknowledge the failure.
        # This prevents the confusing case where the assistant says "Here's your query"
        # but the query actually failed to execute.
        if execution_error and execution_result is None:
            assistant_message = (
                "I wasn't able to generate a working query. "
                f"The last error was:\n\n{execution_error}"
            )

        return DQLGenerationOutcome(
            query=final_query,
            assistant_message=assistant_message,
            execution_result=execution_result,
            execution_error=execution_error,
            used_tables=used_tables,
            phase=DQLPhase.QUERY,
            exploration_results=tuple(exploration_results) if exploration_results else None,
            requires_user_response=False,
        )

    async def _load_registry(
        self, collection_id: str, json_fields: Mapping[str, Iterable[JsonFieldInfo]] | None = None
    ) -> tuple[DQLRegistry, str]:
        """Load the DQL registry and build a schema summary."""
        registry = build_default_registry(collection_id=collection_id, json_fields=json_fields)
        summary = _schema_summary(registry)
        return registry, summary

    def _choose_base_query(
        self, request_query: str | None, messages: Sequence[DQLGeneratorMessage]
    ) -> str | None:
        """Determine the base query to use from the request or message history."""
        if request_query and request_query.strip():
            return _normalize_query(request_query)

        for message in reversed(messages):
            if message.query and message.query.strip():
                return _normalize_query(message.query)
        return None

    def _convert_messages(
        self, messages: Sequence[DQLGeneratorMessage]
    ) -> list[UserMessage | AssistantMessage | SystemMessage]:
        """Convert DQLGeneratorMessage list to LLM message types."""
        converted: list[UserMessage | AssistantMessage | SystemMessage] = []
        for message in messages:
            content = message.content
            if message.query:
                content = f"{content.rstrip()}\n\nDQL query:\n{message.query}"

            if message.role == "assistant":
                converted.append(AssistantMessage(content=content))
            elif message.role == "system":
                converted.append(SystemMessage(content=content))
            else:
                converted.append(UserMessage(content=content))
        return converted

    async def generate(
        self,
        *,
        ctx: ViewContext,
        messages: Sequence[DQLGeneratorMessage],
        current_query: str | None = None,
        model_override: ModelOption | None = None,
        json_fields: Mapping[str, Iterable[JsonFieldInfo]] | None = None,
        rubric_schemas: Sequence[RubricSchemaInfo] | None = None,
    ) -> DQLGenerationOutcome:
        """Generate a DQL query from the conversation history.

        Uses a three-phase workflow:
        1. Clarification: Ask questions if the request is unclear (returns immediately)
        2. Exploration: Run sample queries to discover data values (auto-continues to query)
        3. Query: Generate and execute the final query with retry logic

        Args:
            ctx: The view context with user and collection info.
            messages: The conversation history.
            current_query: Optional current query in the editor.
            model_override: Optional model to use instead of defaults.
            json_fields: Optional pre-loaded JSON field metadata.
            rubric_schemas: Optional rubric output schema information.

        Returns:
            A DQLGenerationOutcome with the generated query and execution results.
        """
        if ctx.user is None:
            raise ValueError("User context is required to generate DQL.")

        if len(messages) == 0:
            raise ValueError("At least one message is required to generate DQL.")

        registry, schema_summary = await self._load_registry(ctx.collection_id, json_fields)
        base_query = self._choose_base_query(current_query, messages)
        base_query_pretty = _prettify_base_query(base_query, registry, ctx.collection_id)
        available_tables = frozenset(t.name for t in registry.iter_tables())
        system_prompt = _build_system_prompt(
            schema_summary, base_query_pretty or base_query, available_tables, rubric_schemas
        )

        converted_messages = self._convert_messages(messages)
        base_messages: list[UserMessage | AssistantMessage | SystemMessage] = [
            SystemMessage(content=system_prompt),
            *converted_messages,
        ]

        model_options = [model_override] if model_override else PROVIDER_PREFERENCES.dql_generator

        # Call LLM and parse phase response
        try:
            raw_text = await self._call_llm(base_messages, model_options)
            phase_response = _parse_phase_response(raw_text)
        except Exception as exc:
            logger.info("Initial LLM call failed: %s", exc)
            return DQLGenerationOutcome(
                query="",
                assistant_message="",
                execution_result=None,
                execution_error=f"Failed to generate response: {exc}",
                used_tables=[],
                phase=DQLPhase.QUERY,
                requires_user_response=False,
            )

        # Route to appropriate phase handler
        if phase_response.phase == DQLPhase.CLARIFICATION:
            return self._handle_clarification_phase(phase_response)

        if phase_response.phase == DQLPhase.EXPLORATION:
            return await self._handle_exploration_phase(
                phase_response,
                ctx,
                schema_summary,
                base_query_pretty or base_query,
                base_messages,
                registry,
                model_options,
                rubric_schemas,
            )

        # Query phase
        return await self._handle_query_phase(
            phase_response,
            ctx,
            schema_summary,
            base_query_pretty or base_query,
            base_messages,
            registry,
            model_options,
            rubric_schemas,
        )
