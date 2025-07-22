import asyncio
import base64
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, TypedDict, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2

from docent._log_util import get_logger
from docent.data_models import AgentRun, BaseAgentRunMetadata, Transcript
from docent.data_models.chat import ChatMessage, parse_chat_message
from docent.data_models.chat.tool import ToolCall
from docent_core._db_service.schemas.auth_models import User
from docent_core._db_service.service import MonoService
from docent_core._server._broker.redis_client import REDIS
from docent_core._server._dependencies.database import get_mono_svc
from docent_core._server._dependencies.user import get_authenticated_user

logger = get_logger(__name__)

# Redis key patterns for trace accumulation
_TRACE_SPANS_KEY_PREFIX = "trace_spans:"
_TRACE_TIMEOUT_KEY_PREFIX = "trace_timeout:"
_TRACE_TIMEOUT_SECONDS = 15 * 60  # Timeout for trace completion


async def _add_spans_to_accumulation(trace_id: str, spans: List[Dict[str, Any]]) -> None:
    """Add spans to accumulation using Redis."""
    trace_key = f"{_TRACE_SPANS_KEY_PREFIX}{trace_id}"

    # Add spans to Redis list
    for span in spans:
        await REDIS.lpush(trace_key, json.dumps(span))  # type: ignore

    # Set TTL for automatic cleanup if trace doesn't complete
    await REDIS.expire(trace_key, _TRACE_TIMEOUT_SECONDS)  # type: ignore


async def _get_accumulated_spans(trace_id: str) -> List[Dict[str, Any]]:
    """Get accumulated spans for a trace from Redis."""
    trace_key = f"{_TRACE_SPANS_KEY_PREFIX}{trace_id}"

    # Get all spans from Redis list
    span_jsons = cast(List[str], await REDIS.lrange(trace_key, 0, -1))  # type: ignore

    spans: List[Dict[str, Any]] = []
    for span_json in reversed(list(span_jsons)):
        try:
            spans.append(json.loads(span_json))
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode span JSON for trace {trace_id}: {e}")
            continue

    return spans


async def _remove_trace_from_accumulation(trace_id: str) -> None:
    """Remove a trace from accumulation in Redis."""
    trace_key = f"{_TRACE_SPANS_KEY_PREFIX}{trace_id}"
    await REDIS.delete(trace_key)


async def _cancel_and_remove_trace_task(trace_id: str) -> None:
    """Cancel and remove a trace completion task from Redis."""
    timeout_key = f"{_TRACE_TIMEOUT_KEY_PREFIX}{trace_id}"
    await REDIS.delete(timeout_key)


def schedule_trace_timeout(trace_id: str, user: User) -> None:
    """Schedule a timeout task for trace completion using Redis."""

    async def timeout_handler():
        await asyncio.sleep(_TRACE_TIMEOUT_SECONDS)

        # Check if trace still exists and hasn't been processed
        timeout_key = f"{_TRACE_TIMEOUT_KEY_PREFIX}{trace_id}"

        # Only process if this worker still owns the timeout
        if await REDIS.exists(timeout_key):  # type: ignore
            accumulated_spans = await _get_accumulated_spans(trace_id)
            if accumulated_spans:
                logger.info(f"Trace {trace_id} timed out, processing accumulated spans")
                await process_completed_trace(trace_id, accumulated_spans, user)
                await _remove_trace_from_accumulation(trace_id)
                await _cancel_and_remove_trace_task(trace_id)

        # Use Redis to ensure only one worker handles the timeout

    async def _schedule_with_lock():
        timeout_key = f"{_TRACE_TIMEOUT_KEY_PREFIX}{trace_id}"

        # Try to set the timeout key (only succeeds if it doesn't exist)
        if await REDIS.set(timeout_key, "1", ex=_TRACE_TIMEOUT_SECONDS, nx=True):  # type: ignore
            # This worker owns the timeout, schedule the task
            asyncio.create_task(timeout_handler())
        else:
            # Another worker already owns the timeout
            logger.debug(f"Timeout for trace {trace_id} already scheduled by another worker")

    # Run the lock-protected operation
    asyncio.create_task(_schedule_with_lock())


class AgentRunData(TypedDict):
    collection_id: str
    agent_run_id: str
    transcripts: Dict[str, Transcript]


telemetry_router = APIRouter()


@telemetry_router.post("/v1/traces")
async def trace_endpoint(
    request: Request,
    user: User = Depends(get_authenticated_user),
    mono_svc: MonoService = Depends(get_mono_svc),
):
    """
    Direct trace endpoint for OpenTelemetry collector HTTP exporter.

    This endpoint accepts OTLP HTTP format telemetry data and logs it.
    Requires authentication via bearer token (API key) in the Authorization header.
    """
    try:
        # Check content type
        content_type = request.headers.get("content-type", "")

        # Read the request body
        body = await request.body()

        # Handle compressed data if needed
        if request.headers.get("content-encoding") == "gzip":
            import gzip

            body = gzip.decompress(body)

        # Process based on content type
        if "application/x-protobuf" in content_type:
            # Handle protobuf format
            trace_data = process_protobuf_traces(body)
        elif "application/json" in content_type:
            # Handle JSON format
            trace_data = process_json_traces(body)
        else:
            raise HTTPException(status_code=415, detail=f"Unsupported content type: {content_type}")

        print(f"Headers: {dict(request.headers)}")

        # Store the raw telemetry data for request
        await mono_svc.store_telemetry_log(user.id, trace_data)

        # Process the traces
        processing_result = await process_traces(trace_data, user)

        # Return success response
        return JSONResponse(
            status_code=200, content={"status": "success", "processed": processing_result["count"]}
        )

    except Exception as e:
        logger.error(f"Error processing traces: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def process_protobuf_traces(body: bytes) -> Dict[str, Any]:
    """Process protobuf formatted trace data."""
    try:
        # Parse the protobuf message
        export_request = trace_service_pb2.ExportTraceServiceRequest()
        export_request.ParseFromString(body)

        # Convert to dictionary for easier processing
        trace_data = MessageToDict(export_request, preserving_proto_field_name=True)
        return trace_data
    except Exception as e:
        logger.error(f"Error parsing protobuf traces: {str(e)}")
        raise ValueError(f"Invalid protobuf format: {str(e)}")


def process_json_traces(body: bytes) -> Dict[str, Any]:
    """Process JSON formatted trace data."""
    try:
        # Decode and parse JSON
        trace_data = json.loads(body.decode("utf-8"))
        return trace_data
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing JSON traces: {str(e)}")
        raise ValueError(f"Invalid JSON format: {str(e)}")


async def process_traces(trace_data: Dict[str, Any], user: User) -> Dict[str, Any]:
    """
    Process the trace data - extract spans, accumulate them, and detect trace completion.

    Args:
        trace_data: Dictionary containing OTLP trace data

    Returns:
        Processing result with statistics
    """
    processed_spans: List[Dict[str, Any]] = []
    total_spans = 0

    try:
        # Extract resource spans
        resource_spans = trace_data.get("resource_spans", [])

        for resource_span in resource_spans:
            # Extract resource attributes
            resource = resource_span.get("resource", {})
            resource_attrs = extract_attributes(resource.get("attributes", []))

            # Process scope spans
            scope_spans = resource_span.get("scope_spans", [])

            for scope_span in scope_spans:
                # Extract scope information
                scope = scope_span.get("scope", {})
                scope_name = scope.get("name", "unknown")
                scope_version = scope.get("version", "")

                # Process individual spans
                spans = scope_span.get("spans", [])

                for span in spans:
                    processed_span = otel_span_format_to_dict(
                        span, resource_attrs, scope_name, scope_version
                    )
                    processed_spans.append(processed_span)
                    total_spans += 1

        # Accumulate spans and check for trace completion
        await accumulate_and_check_completion(processed_spans, user)

        return {
            "count": total_spans,
            "resource_count": len(resource_spans),
            "spans": processed_spans,
        }

    except Exception as e:
        logger.error(f"Error in trace processing: {str(e)}")
        raise


def _extract_single_value(value: Dict[str, Any]) -> Any:
    """Extract a single value from OTLP format based on its type."""
    if "string_value" in value:
        return value["string_value"]
    elif "int_value" in value:
        return int(value["int_value"])
    elif "double_value" in value:
        return float(value["double_value"])
    elif "bool_value" in value:
        return bool(value["bool_value"])
    elif "array_value" in value:
        return extract_array_value(value["array_value"])
    elif "kvlist_value" in value:
        return extract_kvlist_value(value["kvlist_value"])
    else:
        return None


def extract_attributes(attributes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Extract attributes from OTLP format to a simple dictionary.

    Example input (OTLP format):
        [
            {"key": "service.name", "value": {"string_value": "my-service"}},
            {"key": "foo", "value": {"int_value": 42}},
            {"key": "bar", "value": {"bool_value": True}},
            {"key": "tags", "value": {"array_value": {"values": [
                {"string_value": "a"}, {"string_value": "b"}
            ]}}},
        ]

    Example output:
        {
            "service.name": "my-service",
            "foo": 42,
            "bar": True,
            "tags": ["a", "b"]
        }
    """
    result: Dict[str, Any] = {}

    for attr in attributes:
        key = attr.get("key", "")
        value = attr.get("value", {})
        result[key] = _extract_single_value(value)

    return result


def extract_array_value(array_value: Dict[str, Any]) -> List[Any]:
    """Extract array values from OTLP format."""
    values: List[Any] = []
    for item in array_value.get("values", []):
        extracted_value = _extract_single_value(item)
        if extracted_value is not None:
            values.append(extracted_value)
    return values


def extract_kvlist_value(kvlist: Dict[str, Any]) -> Dict[str, Any]:
    """Extract key-value list from OTLP format."""
    return extract_attributes(kvlist.get("values", []))


def otel_span_format_to_dict(
    span: Dict[str, Any], resource_attrs: Dict[str, Any], scope_name: str, scope_version: str
) -> Dict[str, Any]:
    """Process a single span and extract relevant information."""

    # Extract span details
    span_id = span.get("span_id", "")
    trace_id = span.get("trace_id", "")
    parent_span_id = span.get("parent_span_id", "")

    # Convert IDs from base64 if necessary
    if isinstance(span_id, str) and span_id:
        span_id = base64.b64decode(span_id).hex()
    if isinstance(trace_id, str) and trace_id:
        trace_id = base64.b64decode(trace_id).hex()
    if isinstance(parent_span_id, str) and parent_span_id:
        parent_span_id = base64.b64decode(parent_span_id).hex()

    # Extract timestamps (convert from nanoseconds) and ensure timezone-aware (UTC)
    start_time_ns = int(span.get("start_time_unix_nano", 0))
    end_time_ns = int(span.get("end_time_unix_nano", 0))
    start_time = datetime.fromtimestamp(start_time_ns / 1e9, tz=timezone.utc)
    end_time = datetime.fromtimestamp(end_time_ns / 1e9, tz=timezone.utc)
    duration_ms = (end_time_ns - start_time_ns) / 1e6

    # Extract span attributes
    span_attrs = extract_attributes(span.get("attributes", []))

    # Extract events
    events: List[Dict[str, Any]] = []
    for event in span.get("events", []):
        events.append(
            {
                "name": event.get("name", ""),
                "timestamp": datetime.fromtimestamp(
                    int(event.get("time_unix_nano", 0)) / 1e9, tz=timezone.utc
                ).isoformat(),
                "attributes": extract_attributes(event.get("attributes", [])),
            }
        )

    # Extract links
    links: List[Dict[str, Any]] = []
    for link in span.get("links", []):
        link_trace_id = link.get("trace_id", "")
        link_span_id = link.get("span_id", "")

        if isinstance(link_trace_id, str) and link_trace_id:
            link_trace_id = base64.b64decode(link_trace_id).hex()
        if isinstance(link_span_id, str) and link_span_id:
            link_span_id = base64.b64decode(link_span_id).hex()

        links.append(
            {
                "trace_id": link_trace_id,
                "span_id": link_span_id,
                "attributes": extract_attributes(link.get("attributes", [])),
            }
        )

    # Build the processed span
    processed_span: Dict[str, Any] = {
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": parent_span_id,
        "operation_name": span.get("name", ""),
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "duration_ms": duration_ms,
        "status": {
            "code": span.get("status", {}).get("code", 0),
            "message": span.get("status", {}).get("message", ""),
        },
        "kind": span.get("kind", 0),
        "resource_attributes": resource_attrs,
        "span_attributes": span_attrs,
        "events": events,
        "links": links,
        "scope": {"name": scope_name, "version": scope_version},
    }

    return processed_span


async def accumulate_and_check_completion(spans: List[Dict[str, Any]], user: User) -> None:
    """
    Accumulate spans and check for trace completion.

    Args:
        spans: List of processed spans to accumulate
    """
    # Group spans by trace_id for efficient processing
    spans_by_trace: Dict[str, List[Dict[str, Any]]] = {}
    for span in spans:
        trace_id = span.get("trace_id")
        if trace_id:
            if trace_id not in spans_by_trace:
                spans_by_trace[trace_id] = []
            spans_by_trace[trace_id].append(span)

    # Add spans to accumulation using targeted locks
    for trace_id, trace_spans in spans_by_trace.items():
        await _add_spans_to_accumulation(trace_id, trace_spans)

    # Check for trace completion after all spans are accumulated
    for span in spans:
        trace_id = span.get("trace_id")
        if not trace_id:
            continue

        # Get accumulated spans for this trace
        accumulated_spans = await _get_accumulated_spans(trace_id)

        # Check if this span indicates trace completion
        if is_trace_complete(span, accumulated_spans):
            # Process the completed trace with all accumulated spans
            await process_completed_trace(trace_id, accumulated_spans, user)

            # Clean up using targeted locks
            await _remove_trace_from_accumulation(trace_id)
            await _cancel_and_remove_trace_task(trace_id)
        else:
            # Schedule timeout for trace completion
            schedule_trace_timeout(trace_id, user)


def is_trace_complete(span: Dict[str, Any], all_spans: List[Dict[str, Any]]) -> bool:
    """
    Check if a trace is complete based on span status and structure.

    Args:
        span: The current span being processed
        all_spans: All spans in the trace

    Returns:
        True if the trace appears to be complete
    """
    # Check if this is a root span (no parent)
    if not span.get("parent_span_id"):
        return True

    return False


async def process_completed_trace(trace_id: str, spans: List[Dict[str, Any]], user: User) -> None:
    """
    Process a completed trace by creating collections, agent runs, and transcripts.

    Args:
        trace_id: The trace ID that was completed
        spans: All spans in the completed trace
    """
    logger.info(f"Processing completed trace {trace_id} with {len(spans)} spans")

    # Process spans to create agent runs
    await store_spans(spans, user)


async def store_spans(spans: List[Dict[str, Any]], user: User) -> None:
    """
    Store spans by creating collections, agent runs, and transcripts.

    Args:
        spans: List of processed span dictionaries
    """
    if not spans:
        return

    # Initialize database service
    mono_svc = await MonoService.init()

    # Organize spans by collection_id -> agent_run_id -> transcript_id -> spans[]
    organized_spans: Dict[str, Dict[str, Dict[str, List[Dict[str, Any]]]]] = {}

    for span in spans:
        # Extract IDs from span attributes
        span_attrs = span.get("span_attributes", {})
        collection_id = span_attrs.get("collection_id")
        agent_run_id = span_attrs.get("agent_run_id")
        transcript_id = span_attrs.get("transcript_id")

        if not collection_id or not agent_run_id:
            logger.warning(
                f"Skipping span {span.get('span_id')} - missing collection_id or agent_run_id"
            )
            # pprint the json span
            print(json.dumps(span, indent=2))
            continue

        # Use setdefault to organize spans
        organized_spans.setdefault(collection_id, {}).setdefault(agent_run_id, {}).setdefault(
            transcript_id, []
        ).append(span)

    # Process each collection and its agent runs
    total_agent_runs = 0

    for collection_id, agent_runs in organized_spans.items():
        # Extract service name from the first span in this collection
        collection_name = ""
        for agent_run_id, transcripts in agent_runs.items():
            for transcript_id, transcript_spans in transcripts.items():
                if transcript_spans:
                    # Get service name from resource attributes of the first span
                    first_span = transcript_spans[0]
                    resource_attributes = first_span.get("resource_attributes", {})
                    collection_name = resource_attributes.get("service.name", "")
                    if collection_name:
                        break

        # Create collection if it doesn't exist
        try:
            if not await mono_svc.collection_exists(collection_id):
                await mono_svc.create_collection(
                    user=user,
                    collection_id=collection_id,
                    name=collection_name,
                    description="",
                )
                logger.info(
                    f"Created collection {collection_id} with service name: {collection_name}"
                )
        except Exception as e:
            logger.error(f"Error creating/checking collection {collection_id}: {str(e)}")
            continue

        # Process agent runs for this collection
        collection_agent_runs: List[AgentRun] = []

        for agent_run_id, transcripts in agent_runs.items():
            logger.info(f"Processing agent_run_id: {agent_run_id}")
            agent_run_transcripts: Dict[str, Transcript] = {}
            agent_run_scores: Dict[str, int | float | bool | None] = {}
            agent_run_model: str | None = None

            # Process each transcript
            for transcript_id, transcript_spans in transcripts.items():
                logger.info(
                    f"  Processing transcript_id: {transcript_id} with {len(transcript_spans)} spans"
                )

                # store all the chat threads
                chat_threads: List[List[ChatMessage]] = []

                for span in transcript_spans:
                    # Check for agent_run_score events
                    for event in span.get("events", []):
                        if event.get("name") == "agent_run_score":
                            score_name = event.get("attributes", {}).get("score.name")
                            score_value = event.get("attributes", {}).get("score.value")
                            if score_name and score_value is not None:
                                agent_run_scores[score_name] = score_value
                                logger.info(f"    Found score: {score_name} = {score_value}")

                    # Extract model from span attributes
                    span_attrs = span.get("span_attributes", {})
                    if not agent_run_model and "gen_ai.response.model" in span_attrs:
                        agent_run_model = span_attrs["gen_ai.response.model"]
                        logger.info(f"    Found model: {agent_run_model}")

                    # Extract messages from this span
                    span_messages = _span_to_chat_message(span)

                    if not span_messages:
                        continue

                    # look at each span (which will include the chat history, if any)
                    # if there is only 1 message it's a new chat thread
                    # if there are multiple messages we need to find the chat thread it's continuing
                    # by matching the span messages (+role and order) to the existing chat threads
                    # if we find a match, we add any new messages to the existing chat thread
                    # if we don't find a match, we create a new chat thread

                    if len(span_messages) == 1:
                        # Single message - create new chat thread
                        chat_threads.append(span_messages)
                        logger.debug(f"    Created new chat thread with 1 message")
                    else:
                        # Multiple messages - try to find matching existing thread
                        matched_thread_index = None

                        for i, existing_thread in enumerate(chat_threads):
                            # Check if the beginning of span_messages matches the existing thread
                            if len(span_messages) > len(existing_thread):
                                # Check if existing thread is a prefix of span_messages
                                if span_messages[: len(existing_thread)] == existing_thread:
                                    matched_thread_index = i
                                    break

                        if matched_thread_index is not None:
                            # Found matching thread - add new messages
                            existing_thread = chat_threads[matched_thread_index]
                            new_messages = span_messages[len(existing_thread) :]
                            chat_threads[matched_thread_index].extend(new_messages)
                            logger.debug(
                                f"    Extended chat thread {matched_thread_index} with {len(new_messages)} new messages"
                            )
                        else:
                            # No match found - create new chat thread
                            chat_threads.append(span_messages)
                            logger.debug(
                                f"    Created new chat thread with {len(span_messages)} messages"
                            )

                # update this to record each chat thread as a transcript
                if chat_threads:
                    # Create a transcript for each chat thread
                    for i, chat_thread in enumerate(chat_threads):
                        # Create unique transcript ID for each thread
                        thread_transcript_id = str(uuid.uuid4())

                        transcript = Transcript(
                            id=thread_transcript_id,
                            messages=chat_thread,
                            name=f"Chat Thread {i + 1}" if len(chat_threads) > 1 else "",
                            description="",
                        )
                        agent_run_transcripts[thread_transcript_id] = transcript
                        logger.info(
                            f"    Created transcript {thread_transcript_id} with {len(chat_thread)} messages"
                        )
                else:
                    logger.warning(
                        f"    No messages extracted from {len(transcript_spans)} spans for transcript {transcript_id}"
                    )
                    # Log span details for debugging
                    for i, span in enumerate(transcript_spans):
                        span_attrs = span.get("span_attributes", {})
                        logger.debug(
                            f"      Span {i}: {span.get('operation_name')} - keys: {list(span_attrs.keys())}"
                        )

                    # Create agent run if it has transcripts
            if agent_run_transcripts:
                # Create metadata with scores and model using BaseAgentRunMetadata
                metadata_dict: Dict[str, Any] = {"scores": agent_run_scores}
                if agent_run_model:
                    metadata_dict["model"] = agent_run_model

                metadata = BaseAgentRunMetadata(**metadata_dict)
                agent_run = AgentRun(
                    id=agent_run_id,
                    name="",
                    description="",
                    transcripts=agent_run_transcripts,
                    metadata=metadata,
                )
                collection_agent_runs.append(agent_run)
                logger.info(
                    f"  Created agent run {agent_run_id} with {len(agent_run_transcripts)} transcripts, {len(agent_run_scores)} scores, and model: {agent_run_model or 'unknown'}"
                )
            else:
                logger.warning(f"  No transcripts created for agent_run_id: {agent_run_id}")
                # Log transcript details for debugging
                for transcript_id, transcript_spans in transcripts.items():
                    logger.debug(f"    Transcript {transcript_id}: {len(transcript_spans)} spans")

        # Add agent runs to this collection
        if collection_agent_runs:
            try:
                # Get or create default view context for this collection
                ctx = await mono_svc.get_default_view_ctx(collection_id, user)

                # Add agent runs using the existing service method
                await mono_svc.add_agent_runs(ctx, collection_agent_runs)
                logger.info(
                    f"Added {len(collection_agent_runs)} agent runs to collection {collection_id}"
                )
                total_agent_runs += len(collection_agent_runs)
            except Exception as e:
                logger.error(f"Error adding agent runs to collection {collection_id}: {str(e)}")
        else:
            logger.warning(f"No agent runs created for collection {collection_id}")
            # Log agent run details for debugging
            for agent_run_id, transcripts in agent_runs.items():
                logger.debug(f"  Agent run {agent_run_id}: {len(transcripts)} transcripts")

    logger.info(f"Processed {len(spans)} spans into {total_agent_runs} agent runs")


def _extract_tool_calls_from_content(content: str) -> tuple[str, list[ToolCall] | None]:
    """Extract tool calls from content that may contain JSON arrays with tool_use objects.

    Args:
        content: The content string that may contain tool calls

    Returns:
        Tuple of (filtered_content, tool_calls) where tool_calls is None if no tool calls found
    """
    tool_calls = None

    # Check if content contains tool calls (JSON array with tool_use objects)
    if content.startswith("[") and content.endswith("]"):
        try:
            content_array = json.loads(content)
            if isinstance(content_array, list):
                content_array_any = cast(List[Any], content_array)
                # Only keep dict items
                dict_items: list[dict[str, Any]] = [
                    i for i in content_array_any if isinstance(i, dict)
                ]
                # Extract tool calls and filter content
                extracted_tool_calls: list[ToolCall] = []
                filtered_content_parts: list[str] = []

                for item in dict_items:
                    tool_type = item.get("type")
                    if tool_type == "tool_use":
                        tool_item: dict[str, Any] = item
                        tool_call = ToolCall(
                            id=str(tool_item.get("id", "")),
                            type="function",
                            function=str(tool_item.get("name", "")),
                            arguments=(
                                tool_item.get("input", {})
                                if isinstance(tool_item.get("input"), dict)
                                else {}
                            ),
                        )
                        extracted_tool_calls.append(tool_call)
                    elif tool_type == "text":
                        filtered_content_parts.append(str(item.get("text", "")))

                # Update content and tool_calls
                if filtered_content_parts:
                    content = "\n".join(filtered_content_parts)
                else:
                    content = ""

                if extracted_tool_calls:
                    tool_calls = extracted_tool_calls
        except json.JSONDecodeError:
            # Not valid JSON, treat as regular content
            pass

    return content, tool_calls


def _extract_tool_calls_from_completion_data(tool_calls_data: dict[str, Any]) -> list[ToolCall]:
    """Extract tool calls from completion message tool_calls data.

    Args:
        tool_calls_data: Dictionary containing tool call data organized by tool index

    Returns:
        List of ToolCall objects
    """
    tool_calls: list[ToolCall] = []

    for tool_index in sorted(tool_calls_data.keys()):
        tool_data = tool_calls_data[tool_index]

        # Parse arguments if present
        arguments: dict[str, Any] = {}
        if "arguments" in tool_data:
            try:
                arguments = json.loads(tool_data["arguments"])
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse tool call arguments: {tool_data['arguments']}")
                arguments = {"raw_arguments": tool_data["arguments"]}

        tool_call = ToolCall(
            id=tool_data.get("id", ""),
            type="function",
            function=tool_data.get("name", ""),
            arguments=arguments,
        )
        tool_calls.append(tool_call)

    return tool_calls


def _span_to_chat_message(span: Dict[str, Any]) -> List[ChatMessage]:
    """Convert a span to a list of chat message objects."""
    span_attrs = span.get("span_attributes", {})
    messages: List[ChatMessage] = []

    # Debug logging
    span_id = span.get("span_id", "unknown")
    operation_name = span.get("operation_name", "unknown")
    logger.debug(f"Processing span {span_id} ({operation_name}) with {len(span_attrs)} attributes")

    # Extract prompt messages from gen_ai.prompt.{index}.role/content format
    prompt_messages: Dict[int, Dict[str, Any]] = {}

    for key, value in span_attrs.items():
        prefix = "gen_ai.prompt."
        if key.startswith(prefix) and "." in key[len(prefix) :]:
            # Extract index and field (role or content)
            parts = key[len(prefix) :].split(".", 1)
            if len(parts) == 2:
                try:
                    index = int(parts[0])
                    field = parts[1]
                    if field in ["role", "content"]:
                        if index not in prompt_messages:
                            prompt_messages[index] = {}
                        prompt_messages[index][field] = str(value)
                except Exception as e:
                    logger.error(f"Failed to parse prompt message key '{key}': {e}")
                    continue

    # Convert prompt messages to ChatMessage objects
    for index in sorted(prompt_messages.keys()):
        msg_data = prompt_messages[index]
        if "role" in msg_data and "content" in msg_data:
            try:
                # Handle tool calls embedded in content for prompt messages
                content, tool_calls = _extract_tool_calls_from_content(msg_data["content"])

                message_data = {
                    "role": msg_data["role"],
                    "content": content,
                }

                # Add tool_calls if present
                if tool_calls:
                    message_data["tool_calls"] = tool_calls

                message = parse_chat_message(message_data)
                messages.append(message)
            except ValueError as e:
                logger.error(
                    f"Invalid role '{msg_data['role']}' in span {span.get('span_id')} at prompt index {index}: {e}"
                )
                continue
            except Exception as e:
                logger.error(f"Failed to parse message at index {index}: {e}")
                continue

    # Extract completion messages from gen_ai.completion.{index}.role/content/tool_calls format
    completion_messages: Dict[int, Dict[str, Any]] = {}

    for key, value in span_attrs.items():
        prefix = "gen_ai.completion."
        if key.startswith(prefix) and "." in key[len(prefix) :]:
            # Extract index and field (role, content, or tool_calls)
            parts = key[len(prefix) :].split(".", 1)
            if len(parts) == 2:
                try:
                    index = int(parts[0])
                    field = parts[1]
                    if field in ["role", "content"]:
                        if index not in completion_messages:
                            completion_messages[index] = {}
                        completion_messages[index][field] = str(value)
                    elif field.startswith("tool_calls."):
                        # Handle tool calls: gen_ai.completion.{index}.tool_calls.{tool_index}.{field}
                        tool_parts = field.split(".", 2)
                        if len(tool_parts) >= 3:
                            tool_index = int(tool_parts[1])
                            tool_field = tool_parts[2]

                            if index not in completion_messages:
                                completion_messages[index] = {}
                            if "tool_calls" not in completion_messages[index]:
                                completion_messages[index]["tool_calls"] = {}
                            if tool_index not in completion_messages[index]["tool_calls"]:
                                completion_messages[index]["tool_calls"][tool_index] = {}

                            completion_messages[index]["tool_calls"][tool_index][tool_field] = str(
                                value
                            )
                except Exception as e:
                    logger.error(f"Failed to parse completion message key '{key}': {e}")
                    continue

    # Convert completion messages to ChatMessage objects
    for index in sorted(completion_messages.keys()):
        msg_data = completion_messages[index]
        if "role" in msg_data and "content" in msg_data:
            try:
                message_data = {
                    "role": msg_data["role"],
                    "content": msg_data["content"],
                }

                # Add tool calls if present
                if "tool_calls" in msg_data:
                    tool_calls = _extract_tool_calls_from_completion_data(msg_data["tool_calls"])
                    if tool_calls:
                        message_data["tool_calls"] = tool_calls

                completion_message = parse_chat_message(message_data)
                messages.append(completion_message)
            except ValueError as e:
                logger.error(
                    f"Invalid completion role '{msg_data['role']}' in span {span.get('span_id')} at completion index {index}: {e}"
                )
            except Exception as e:
                logger.error(f"Failed to parse completion message at index {index}: {e}")

    # Debug logging
    if messages:
        logger.debug(f"Extracted {len(messages)} messages from span {span_id}")
    else:
        logger.debug(
            f"No messages extracted from span {span_id} - prompt_messages: {len(prompt_messages)}, completion_messages: {len(completion_messages)}"
        )

    return messages
