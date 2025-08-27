import asyncio
import base64
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, cast
from uuid import uuid4

from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2
from redis.exceptions import LockError
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from docent._log_util import get_logger
from docent.data_models import (
    AgentRun,
    Transcript,
    TranscriptGroup,
)
from docent.data_models.chat import ChatMessage, parse_chat_message
from docent.data_models.chat.tool import ToolCall
from docent_core._server._analytics.posthog import AnalyticsClient
from docent_core._server._broker.redis_client import get_redis_client
from docent_core.docent.db.contexts import ViewContext
from docent_core.docent.db.schemas.auth_models import User
from docent_core.docent.db.schemas.tables import (
    SQLAAgentRun,
    SQLATelemetryLog,
    SQLATranscript,
    SQLATranscriptGroup,
)
from docent_core.docent.services.monoservice import MonoService
from docent_core.docent.services.telemetry_accumulation import TelemetryAccumulationService

logger = get_logger(__name__)
# Redis lock prefix for store_spans operations
_STORE_SPANS_LOCK_PREFIX = "store_spans:"


class TelemetryService:
    def __init__(self, session: AsyncSession, mono_svc: MonoService):
        self.session = session
        self.mono_svc = mono_svc

    ###################
    # Telemetry Logs  #
    ###################

    async def store_telemetry_log(
        self,
        user_id: str,
        type: str,
        version: str,
        json_data: dict[str, Any],
        *,
        collection_id: str | None = None,
    ) -> str:
        """Store telemetry log data in the database."""
        telemetry_id = str(uuid4())
        self.session.add(
            SQLATelemetryLog(
                id=telemetry_id,
                user_id=user_id,
                collection_id=collection_id,
                type=type,
                version=version,
                json_data=json_data,
            )
        )
        return telemetry_id

    async def update_telemetry_log_collection_id(self, telemetry_id: str, collection_id: str):
        """Update the collection ID for a telemetry log entry."""
        await self.session.execute(
            update(SQLATelemetryLog)
            .where(SQLATelemetryLog.id == telemetry_id)
            .values(collection_id=collection_id)
        )

    async def get_telemetry_log(self, telemetry_id: str) -> SQLATelemetryLog | None:
        """Get a telemetry log entry by ID."""
        result = await self.session.execute(
            select(SQLATelemetryLog).where(SQLATelemetryLog.id == telemetry_id)
        )
        return result.scalar_one_or_none()

    async def get_telemetry_logs_by_user(
        self, user_id: str, limit: int = 100
    ) -> list[SQLATelemetryLog]:
        """Get telemetry logs for a user, ordered by creation time (newest first)."""
        result = await self.session.execute(
            select(SQLATelemetryLog)
            .where(SQLATelemetryLog.user_id == user_id)
            .order_by(SQLATelemetryLog.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_telemetry_logs_by_collection(
        self, collection_id: str, limit: int = 100
    ) -> list[SQLATelemetryLog]:
        """Get telemetry logs for a collection, ordered by creation time (newest first)."""
        result = await self.session.execute(
            select(SQLATelemetryLog)
            .where(SQLATelemetryLog.collection_id == collection_id)
            .order_by(SQLATelemetryLog.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    ######################
    # Trace Processing   #
    ######################

    async def handle_new_trace_data(
        self,
        trace_data: Dict[str, Any],
        user: User,
        accumulation_service: TelemetryAccumulationService,
    ) -> int:
        # Extract spans from trace data
        spans = await self.extract_spans(trace_data)

        # Extract unique collection IDs and names from spans
        collection_ids, collection_names = self.extract_collection_info_from_spans(spans)

        # Check permissions for all collections mentioned in spans
        await self.ensure_write_permission_for_collections(collection_ids, user)

        await self.ensure_collections_exist(collection_ids, collection_names, user)

        # Accumulate spans into database
        await self.accumulate_spans(spans, user.id, accumulation_service)

        for collection_id in collection_ids:
            redis_client = await get_redis_client()
            lock_key = f"{_STORE_SPANS_LOCK_PREFIX}{collection_id}"

            try:
                # Use lock to prevent concurrent processing of the same collection
                async with redis_client.lock(lock_key, blocking=False):
                    # Lock acquired, process spans
                    accumulated_spans = await accumulation_service.get_accumulated_spans(
                        collection_id
                    )

                    if accumulated_spans:
                        logger.info(
                            f"Processing collection {collection_id} with {len(accumulated_spans)} spans"
                        )
                        count_agent_runs = await self.store_spans(
                            accumulated_spans, user, accumulation_service
                        )
                        logger.info(
                            f"Successfully processed collection {collection_id} with {count_agent_runs} agent runs"
                        )
                    else:
                        logger.info(f"No accumulated spans for collection {collection_id}")
            except LockError:
                logger.info(
                    f"Collection {collection_id} is already being processed by another request"
                )
                # Continue processing other collections even if one fails
                continue
            except Exception as e:
                logger.error(f"Error processing collection {collection_id}: {str(e)}")
                # Continue processing other collections even if one fails
                continue

        return len(spans)

    def extract_collection_info_from_spans(
        self,
        spans: List[Dict[str, Any]],
    ) -> tuple[set[str], Dict[str, str]]:
        """
        Extract unique collection IDs and names from spans.

        Args:
            spans: List of processed spans

        Returns:
            Tuple of (collection_ids, collection_names)
        """
        collection_ids: set[str] = set()
        collection_names: Dict[str, str] = {}

        for span in spans:
            span_attrs = span.get("attributes", {})
            collection_id = span_attrs.get("collection_id")
            if collection_id and isinstance(collection_id, str):
                collection_ids.add(collection_id)

                # Extract collection name from service.name if not already found
                if collection_id not in collection_names:
                    resource_attributes = span.get("resource_attributes", {})
                    service_name = resource_attributes.get("service.name", "")
                    if service_name:
                        collection_names[collection_id] = service_name

        return collection_ids, collection_names

    async def ensure_collections_exist(
        self, collection_ids: set[str], collection_names: Dict[str, str], user: User
    ) -> None:
        """
        Ensure all collections exist, creating them if necessary.

        Args:
            collection_ids: Set of collection IDs to ensure exist
            collection_names: Dictionary mapping collection IDs to their names
            user: The user creating the collections
        """
        for collection_id in collection_ids:
            try:
                collection_name = collection_names.get(collection_id)
                await self.ensure_collection_exists(collection_id, user, collection_name)
            except Exception as e:
                logger.error(f"Error creating/checking collection {collection_id}: {str(e)}")
                raise

    async def ensure_collection_exists(
        self, collection_id: str, user: User, collection_name: str | None = None
    ) -> None:
        """
        Ensure a collection exists, creating it with the specified name if it doesn't.
        Update the name if it's currently not set.

        Args:
            collection_id: The collection ID to ensure exists
            collection_name: The name to use for the collection
            user: The user creating the collection
        """
        try:
            if not await self.mono_svc.collection_exists(collection_id):
                await self.mono_svc.create_collection(
                    user=user,
                    collection_id=collection_id,
                    name=collection_name,
                    description="",
                )
                logger.info(f"Created collection {collection_id} with name: {collection_name}")
            else:
                if collection_name:
                    collection = await self.mono_svc.get_collection(collection_id)
                    if collection and not collection.name:
                        await self.mono_svc.update_collection(
                            collection_id=collection_id,
                            name=collection_name,
                        )
        except Exception as e:
            logger.error(f"Error creating collection {collection_id}: {str(e)}")
            raise

    async def ensure_write_permission_for_collections(
        self, collection_ids: set[str], user: User
    ) -> None:
        """
        Check that the user has write permissions on all collections,
        or that the collections don't exist yet (in which case they will be created).

        Args:
            collection_ids: Set of collection IDs to check
            user: The authenticated user

        Raises:
            HTTPException: If user lacks write permissions on any existing collection
        """
        from fastapi import HTTPException

        from docent_core.docent.db.schemas.auth_models import Permission, ResourceType

        # Check permissions for each collection
        for collection_id in collection_ids:
            # Check if collection exists
            collection_exists = await self.mono_svc.collection_exists(collection_id)

            if collection_exists:
                # Collection exists - check write permissions
                has_write_permission = await self.mono_svc.has_permission(
                    user=user,
                    resource_type=ResourceType.COLLECTION,
                    resource_id=collection_id,
                    permission=Permission.WRITE,
                )

                if not has_write_permission:
                    logger.error(
                        f"Permission denied for user {user.id} on collection {collection_id}"
                    )
                    raise HTTPException(
                        status_code=403,
                        detail=f"Write permission required on collection {collection_id}",
                    )
            else:
                # Collection doesn't exist - this is allowed, it will be created later
                logger.info(
                    f"Collection {collection_id} doesn't exist yet, will be created during processing"
                )

    async def ensure_write_permission_for_collection(self, collection_id: str, user: User) -> None:
        """
        Check that the user has write permissions on a single collection,
        or that the collection doesn't exist yet (in which case it will be created).

        Args:
            collection_id: The collection ID to check
            user: The authenticated user

        Raises:
            HTTPException: If user lacks write permissions on the existing collection
        """
        await self.ensure_write_permission_for_collections({collection_id}, user)

    def parse_protobuf_traces(self, body: bytes) -> Dict[str, Any]:
        """Parse protobuf formatted trace data."""
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

    async def extract_spans(self, trace_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract spans from the trace data.

        Args:
            trace_data: Dictionary containing OTLP trace data

        Returns:
            List of extracted spans
        """
        extracted_spans: List[Dict[str, Any]] = []

        try:
            # Extract resource spans
            resource_spans = trace_data.get("resource_spans", [])

            for resource_span in resource_spans:
                # Extract resource attributes
                resource = resource_span.get("resource", {})
                resource_attrs = self.extract_attributes(resource.get("attributes", []))

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
                        extracted_span = self.otel_span_format_to_dict(
                            span, resource_attrs, scope_name, scope_version
                        )
                        extracted_spans.append(extracted_span)

            return extracted_spans

        except Exception as e:
            logger.error(f"Error extracting spans: {str(e)}")
            raise

    def _extract_single_value(self, value: Dict[str, Any]) -> Any:
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
            return self.extract_array_value(value["array_value"])
        elif "kvlist_value" in value:
            return self.extract_kvlist_value(value["kvlist_value"])
        else:
            return None

    def extract_attributes(self, attributes: List[Dict[str, Any]]) -> Dict[str, Any]:
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
            result[key] = self._extract_single_value(value)

        return result

    def extract_array_value(self, array_value: Dict[str, Any]) -> List[Any]:
        """Extract array values from OTLP format."""
        values: List[Any] = []
        for item in array_value.get("values", []):
            extracted_value = self._extract_single_value(item)
            if extracted_value is not None:
                values.append(extracted_value)
        return values

    def extract_kvlist_value(self, kvlist: Dict[str, Any]) -> Dict[str, Any]:
        """Extract key-value list from OTLP format."""
        return self.extract_attributes(kvlist.get("values", []))

    def otel_span_format_to_dict(
        self,
        span: Dict[str, Any],
        resource_attrs: Dict[str, Any],
        scope_name: str,
        scope_version: str,
    ) -> Dict[str, Any]:
        """Process a single span and extract relevant information, preserving any additional fields."""

        # Extract and convert span details
        raw_span_id = span.get("span_id", "")
        raw_trace_id = span.get("trace_id", "")
        raw_parent_span_id = span.get("parent_span_id", "")

        # Convert IDs from base64 if necessary
        span_id = raw_span_id
        trace_id = raw_trace_id
        parent_span_id = raw_parent_span_id

        if isinstance(span_id, str) and span_id:
            span_id = base64.b64decode(span_id).hex()
        if isinstance(trace_id, str) and trace_id:
            trace_id = base64.b64decode(trace_id).hex()
        if isinstance(parent_span_id, str) and parent_span_id:
            parent_span_id = base64.b64decode(parent_span_id).hex()

        # Extract timestamps (convert from nanoseconds) and ensure timezone-aware (UTC)
        start_time_ns = int(span.get("start_time_unix_nano", 0))
        end_time_ns = int(span.get("end_time_unix_nano", 0))
        start_time = datetime.fromtimestamp(start_time_ns / 1e9, tz=timezone.utc).isoformat()
        end_time = datetime.fromtimestamp(end_time_ns / 1e9, tz=timezone.utc).isoformat()
        duration_ms = (end_time_ns - start_time_ns) / 1e6

        # Extract span attributes
        span_attrs = self.extract_attributes(span.get("attributes", []))

        # Extract events
        events: List[Dict[str, Any]] = []
        for event in span.get("events", []):
            events.append(
                {
                    "name": event.get("name", ""),
                    "timestamp": datetime.fromtimestamp(
                        int(event.get("time_unix_nano", 0)) / 1e9, tz=timezone.utc
                    ).isoformat(),
                    "attributes": self.extract_attributes(event.get("attributes", [])),
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
                    "attributes": self.extract_attributes(link.get("attributes", [])),
                }
            )
        # Start with a copy of the original span to preserve all fields
        processed_span: Dict[str, Any] = span.copy()
        # Update the processed span with our enhanced fields
        processed_span.update(
            {
                "trace_id": trace_id,
                "span_id": span_id,
                "parent_span_id": parent_span_id,
                "raw_span_id": raw_span_id,
                "raw_trace_id": raw_trace_id,
                "raw_parent_span_id": raw_parent_span_id,
                "operation_name": span.get("name", ""),
                "start_time": start_time,
                "end_time": end_time,
                "duration_ms": duration_ms,
                "status": {
                    "code": span.get("status", {}).get("code", 0),
                    "message": span.get("status", {}).get("message", ""),
                },
                "kind": span.get("kind", 0),
                "resource_attributes": resource_attrs,
                "attributes": span_attrs,
                "events": events,
                "links": links,
                "scope": {"name": scope_name, "version": scope_version},
            }
        )

        return processed_span

    async def accumulate_spans(
        self,
        spans: List[Dict[str, Any]],
        user_id: str | None = None,
        accumulation_service: TelemetryAccumulationService | None = None,
    ) -> None:
        """
        Accumulate spans by collection_id for later processing.

        Args:
            spans: List of processed spans to accumulate
            user_id: Optional user ID for tracking who created the spans
            accumulation_service: Optional service instance to use
        """
        # Group spans by collection_id for efficient processing
        spans_by_collection: Dict[str, List[Dict[str, Any]]] = {}
        for span in spans:
            span_attrs = span.get("attributes", {})
            collection_id = span_attrs.get("collection_id")
            if collection_id:
                if collection_id not in spans_by_collection:
                    spans_by_collection[collection_id] = []
                spans_by_collection[collection_id].append(span)

        # Add spans to accumulation
        for collection_id, collection_spans in spans_by_collection.items():
            if accumulation_service:
                await accumulation_service.add_spans(collection_id, collection_spans, user_id)
            else:
                logger.error("Accumulation service not found, skipping accumulation")

    async def process_completed_collection(
        self,
        collection_id: str,
        spans: List[Dict[str, Any]],
        user: User,
        analytics: AnalyticsClient,
        accumulation_service: TelemetryAccumulationService,
    ) -> None:
        """
        Process a completed collection by creating agent runs, transcripts, and transcript groups.

        Args:
            collection_id: The collection ID that was completed
            spans: All spans in the completed collection
        """
        logger.info(f"Processing completed collection {collection_id} with {len(spans)} spans")

        # Process spans to create agent runs
        agent_run_count = await self.store_spans(spans, user, accumulation_service)

        # Track with PostHog
        analytics.track_event(
            "agent_runs_ingested",
            properties={
                "collection_id": collection_id,
                "num_runs": agent_run_count,
                "source": "tracing",
            },
        )

    async def store_spans(
        self,
        spans: List[Dict[str, Any]],
        user: User,
        accumulation_service: TelemetryAccumulationService | None = None,
    ) -> int:
        """
        Store spans by creating collections, agent runs, and transcripts.

        Args:
            spans: List of processed span dictionaries
            user: The user creating the agent runs

        Returns:
            int: Number of agent runs created
        """
        if not spans:
            return 0

        # Organize spans by collection_id -> agent_run_id -> transcript_id -> spans[]
        spans_by_collection = self._organize_spans_by_collection(spans)

        # Process each collection and its agent runs
        total_agent_runs = 0

        for collection_id, spans_by_agent_run in spans_by_collection.items():
            # Ensure collection exists
            if not await self.mono_svc.collection_exists(collection_id):
                from fastapi import HTTPException

                logger.error(
                    f"Collection {collection_id} does not exist but should have been created earlier"
                )
                raise HTTPException(
                    status_code=404,
                    detail=f"Collection {collection_id} not found. It should have been created during trace processing.",
                )

            # Get or create default view context for this collection
            ctx = await self.mono_svc.get_default_view_ctx(collection_id, user)

            # Get transcript group metadata from database
            transcript_group_metadata: Dict[str, Dict[str, Any]] = {}
            if accumulation_service:
                transcript_group_metadata = (
                    await accumulation_service.get_transcript_group_metadata(collection_id)
                )
            transcript_groups_by_agent_run: Dict[str, List[TranscriptGroup]] = {}

            if transcript_group_metadata:
                transcript_groups = self._create_transcript_groups_from_accumulation_data(
                    transcript_group_metadata
                )
                if transcript_groups:
                    # Group transcript groups by agent_run_id
                    for tg in transcript_groups:
                        if tg.agent_run_id not in transcript_groups_by_agent_run:
                            transcript_groups_by_agent_run[tg.agent_run_id] = []
                        transcript_groups_by_agent_run[tg.agent_run_id].append(tg)
                    logger.info(
                        f"Found {len(transcript_groups)} transcript groups for {len(transcript_groups_by_agent_run)} agent runs"
                    )

            # Create agent runs for this collection with stored scores and metadata
            collection_agent_runs = await self._create_agent_runs_from_spans(
                spans_by_agent_run,
                collection_id,
                transcript_groups_by_agent_run,
                accumulation_service,
            )

            # Add agent runs to this collection
            if collection_agent_runs:
                try:
                    # Add agent runs using the existing service method
                    await self.update_agent_runs_for_telemetry(ctx, collection_agent_runs)
                    logger.info(
                        f"Added {len(collection_agent_runs)} agent runs to collection {collection_id}"
                    )
                    total_agent_runs += len(collection_agent_runs)
                except Exception as e:
                    logger.error(f"Error adding agent runs to collection {collection_id}: {str(e)}")

            else:
                logger.warning(f"No agent runs created for collection {collection_id}")
                # Log agent run details for debugging
                for agent_run_id, transcripts in spans_by_agent_run.items():
                    logger.debug(f"  Agent run {agent_run_id}: {len(transcripts)} transcripts")

        logger.info(f"Processed {len(spans)} spans into {total_agent_runs} agent runs")

        return total_agent_runs

    async def update_agent_runs_for_telemetry(
        self, ctx: ViewContext, agent_runs: Sequence[AgentRun]
    ):
        """
        Update agent runs - create if they don't exist, update if they do exist.
        For transcripts, delete existing ones and recreate them.
        For transcript groups, upsert them with proper parent-child ordering.
        """
        # Convert AgentRun objects to SQLAlchemy objects using existing conversion functions
        agent_run_data: list[SQLAAgentRun] = []
        transcript_data: list[SQLATranscript] = []
        transcript_group_data: list[SQLATranscriptGroup] = []
        agent_run_ids = [ar.id for ar in agent_runs]

        # Check collection size limit
        query = select(func.count()).where(SQLAAgentRun.collection_id == ctx.collection_id)
        result = await self.session.execute(query)
        existing_count = result.scalar_one()

        # Count how many new agent runs we'll be adding (not updating)
        existing_agent_run_query = select(SQLAAgentRun.id).where(
            SQLAAgentRun.collection_id == ctx.collection_id, SQLAAgentRun.id.in_(agent_run_ids)
        )
        existing_agent_run_result = await self.session.execute(existing_agent_run_query)
        existing_agent_run_ids = set(existing_agent_run_result.scalars().all())
        new_agent_run_count = len(agent_run_ids) - len(existing_agent_run_ids)

        if existing_count + new_agent_run_count > 100_000:
            raise ValueError("Number of agent runs in the current collection is too large")

        # Process all agent runs, transcripts, and transcript groups first
        for agent_run in agent_runs:
            # Use the existing from_agent_run method to get all fields properly
            sqla_agent_run = SQLAAgentRun.from_agent_run(agent_run, ctx.collection_id)
            agent_run_data.append(sqla_agent_run)

            # Process transcripts for this agent run
            for key, t in agent_run.transcripts.items():
                # Use the existing from_transcript method to get all fields properly
                sqla_transcript = SQLATranscript.from_transcript(
                    t, key, ctx.collection_id, agent_run.id
                )
                transcript_data.append(sqla_transcript)

            # Process transcript groups for this agent run
            if hasattr(agent_run, "transcript_groups") and agent_run.transcript_groups:
                for tg in agent_run.transcript_groups.values():
                    sqla_transcript_group = SQLATranscriptGroup.from_transcript_group(tg)
                    transcript_group_data.append(sqla_transcript_group)

        # Handle agent runs - upsert (insert or update)
        for sqla_agent_run in agent_run_data:
            # Use merge to handle both insert and update
            await self.session.merge(sqla_agent_run)

        # Handle transcript groups
        if transcript_group_data:
            for sqla_transcript_group in transcript_group_data:
                # Use merge to handle both insert and update
                await self.session.merge(sqla_transcript_group)

        # Validate transcript_group_id references before inserting transcripts
        await self._validate_transcript_group_references(transcript_data)

        # Handle transcripts - delete existing and recreate
        # Delete existing transcripts for these agent runs
        delete_transcript_query = delete(SQLATranscript).where(
            SQLATranscript.agent_run_id.in_(agent_run_ids)
        )
        await self.session.execute(delete_transcript_query)

        # Insert new transcripts
        self.session.add_all(transcript_data)

        logger.info(
            f"Added {len(agent_runs)} agent runs, {len(transcript_data)} transcripts, and {len(transcript_group_data)} transcript groups"
        )

    async def _validate_transcript_group_references(
        self, transcript_data: list[SQLATranscript]
    ) -> None:
        """
        Validate that all transcript_group_id references in transcripts exist in the database.
        If a reference doesn't exist, set it to None to avoid foreign key violations.

        Args:
            transcript_data: List of SQLATranscript objects to validate
        """
        # Collect all unique transcript_group_ids that are not None
        referenced_group_ids: set[str] = set()
        for transcript in transcript_data:
            if transcript.transcript_group_id:
                referenced_group_ids.add(transcript.transcript_group_id)

        if not referenced_group_ids:
            return

        # Check which transcript groups exist in the database
        query = select(SQLATranscriptGroup.id).where(
            SQLATranscriptGroup.id.in_(list(referenced_group_ids))
        )
        result = await self.session.execute(query)
        existing_group_ids = set(result.scalars().all())

        # Find missing transcript groups
        missing_group_ids = referenced_group_ids - existing_group_ids

        if missing_group_ids:
            logger.warning(
                f"Found {len(missing_group_ids)} missing transcript groups: {missing_group_ids}"
            )
            # Set transcript_group_id to None for transcripts referencing missing groups
            for transcript in transcript_data:
                if transcript.transcript_group_id in missing_group_ids:
                    logger.warning(
                        f"Removing reference to missing transcript group {transcript.transcript_group_id} from transcript {transcript.id}"
                    )
                    transcript.transcript_group_id = None

    def _organize_spans_by_collection(
        self,
        spans: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Dict[str, List[Dict[str, Any]]]]]:
        """
        Organize spans by collection_id -> agent_run_id -> transcript_id -> spans[].

        Args:
            spans: List of processed span dictionaries

        Returns:
            Organized spans structure
        """
        organized_spans: Dict[str, Dict[str, Dict[str, List[Dict[str, Any]]]]] = {}

        for span in spans:
            # Extract IDs from span attributes
            span_attrs = span.get("attributes", {})
            collection_id = span_attrs.get("collection_id")
            agent_run_id = span_attrs.get("agent_run_id")
            transcript_id = span_attrs.get("transcript_id")

            if not collection_id:
                span_id = span.get("span_id", "unknown")
                logger.warning(f"Skipping span {span_id} - missing collection_id")
                logger.debug(f"Span: {json.dumps(span, indent=2)}")
                continue

            organized_spans.setdefault(collection_id, {}).setdefault(agent_run_id, {}).setdefault(
                transcript_id, []
            ).append(span)

        return organized_spans

    def _create_transcript_groups_from_accumulation_data(
        self, transcript_group_metadata: Dict[str, Dict[str, Any]]
    ) -> List[TranscriptGroup]:
        """
        Create TranscriptGroup objects from accumulation metadata.

        Args:
            transcript_group_metadata: Dictionary mapping transcript_group_id to merged metadata dict

        Returns:
            List of TranscriptGroup objects
        """
        transcript_groups: List[TranscriptGroup] = []

        for transcript_group_id, metadata in transcript_group_metadata.items():
            if not metadata:
                continue

            # Extract fields from metadata
            name = metadata.get("name")
            description = metadata.get("description")
            agent_run_id = metadata.get("agent_run_id")
            collection_id = metadata.get("collection_id")
            parent_transcript_group_id = metadata.get("parent_transcript_group_id")
            metadata_dict = metadata.get("metadata", {})

            # Skip if required fields are missing
            if not agent_run_id:
                logger.warning(
                    f"Skipping transcript group {transcript_group_id} - missing agent_run_id"
                )
                continue

            if not collection_id:
                logger.warning(
                    f"Skipping transcript group {transcript_group_id} - missing collection_id"
                )
                continue

            # Create TranscriptGroup object
            transcript_group = TranscriptGroup(
                id=transcript_group_id,
                name=name,
                description=description,
                collection_id=collection_id,
                agent_run_id=agent_run_id,
                parent_transcript_group_id=parent_transcript_group_id,
                metadata=metadata_dict if metadata_dict else {},
            )

            transcript_groups.append(transcript_group)

        return transcript_groups

    async def _create_agent_runs_from_spans(
        self,
        agent_run_spans: Dict[str, Dict[str, List[Dict[str, Any]]]],
        collection_id: str,
        transcript_groups_by_agent_run: Dict[str, List[TranscriptGroup]] | None = None,
        accumulation_service: TelemetryAccumulationService | None = None,
    ) -> List[AgentRun]:
        """
        Create AgentRun objects from organized spans, incorporating stored scores and metadata.

        Args:
            agent_runs: Organized spans by agent_run_id -> transcript_id -> spans[]
            collection_id: The ID of the collection these spans belong to

        Returns:
            List of AgentRun objects
        """
        collection_agent_runs: List[AgentRun] = []

        for agent_run_id, transcripts in agent_run_spans.items():
            logger.info(f"Processing agent_run_id: {agent_run_id}")
            agent_run_transcripts: Dict[str, Transcript] = {}
            agent_run_scores: Dict[str, int | float | bool | None] = {}
            agent_run_model: str | None = None
            agent_run_metadata_dict: Dict[str, Any] = {}

            # Process each transcript
            for transcript_id, transcript_spans in transcripts.items():
                logger.info(
                    f"  Processing transcript_id: {transcript_id} with {len(transcript_spans)} spans"
                )

                # Extract metadata and scores from spans
                for span in transcript_spans:
                    # Check for agent_run_score events
                    for event in span.get("events", []):
                        if event.get("name") == "agent_run_score":
                            score_name = event.get("attributes", {}).get("score.name")
                            score_value = event.get("attributes", {}).get("score.value")
                            if score_name and score_value is not None:
                                agent_run_scores[score_name] = score_value
                                logger.info(f"    Found score: {score_name} = {score_value}")

                    # Extract metadata from span events
                    span_metadata = self._extract_metadata_from_span_events(span)
                    if span_metadata:
                        # Unflatten the metadata to restore nested structure
                        unflattened_metadata = self._unflatten_metadata(span_metadata)
                        agent_run_metadata_dict.update(unflattened_metadata)
                        logger.info(f"    Found metadata: {unflattened_metadata}")

                    # Extract model from span attributes
                    span_attrs = span.get("attributes", {})
                    if not agent_run_model and "gen_ai.response.model" in span_attrs:
                        agent_run_model = span_attrs["gen_ai.response.model"]
                        logger.info(f"    Found model: {agent_run_model}")

                # Create transcripts from spans
                transcripts_list = self._create_transcripts_from_spans(transcript_spans)

                # Add transcripts to agent run
                for transcript in transcripts_list:
                    agent_run_transcripts[transcript.id] = transcript

            # Create agent run if it has transcripts
            if agent_run_transcripts:
                # Get stored scores and metadata for this collection
                collection_scores: Dict[str, List[Dict[str, Any]]] = {}
                collection_metadata: Dict[str, List[Dict[str, Any]]] = {}
                if accumulation_service:
                    collection_scores = await accumulation_service.get_collection_scores(
                        collection_id
                    )
                    collection_metadata = await accumulation_service.get_collection_metadata(
                        collection_id
                    )

                # Create metadata with scores, model, and any additional metadata using BaseAgentRunMetadata
                metadata_dict: Dict[str, Any] = {"scores": agent_run_scores}
                if agent_run_model:
                    metadata_dict["model"] = agent_run_model

                # Add any additional metadata from span events
                if agent_run_metadata_dict:
                    metadata_dict.update(agent_run_metadata_dict)
                    logger.info(f"  Added metadata to agent run: {agent_run_metadata_dict}")

                # Add stored scores (these take precedence over span-based scores)
                if collection_scores.get(agent_run_id):
                    for score_item in collection_scores[agent_run_id]:
                        stored_score_name: str | None = score_item.get("score_name")
                        stored_score_value: int | float | bool | str | None = score_item.get(
                            "score_value"
                        )
                        if stored_score_name and stored_score_value is not None:
                            # Add the stored score to the scores dict
                            metadata_dict["scores"][stored_score_name] = stored_score_value
                            logger.info(
                                f"  Added stored score to agent run: {stored_score_name} = {stored_score_value}"
                            )

                # Add stored metadata (these take precedence over span-based metadata)
                if collection_metadata.get(agent_run_id):
                    for metadata_item in collection_metadata[agent_run_id]:
                        stored_metadata: Dict[str, Any] = metadata_item.get("metadata", {})
                        if stored_metadata:
                            # Merge stored metadata with span-based metadata, stored metadata takes precedence
                            metadata_dict.update(stored_metadata)
                            logger.info(f"  Added stored metadata to agent run: {stored_metadata}")

                metadata = metadata_dict

                # Get transcript groups for this agent run
                agent_run_transcript_groups: Dict[str, TranscriptGroup] = {}
                if (
                    transcript_groups_by_agent_run
                    and agent_run_id in transcript_groups_by_agent_run
                ):
                    for tg in transcript_groups_by_agent_run[agent_run_id]:
                        agent_run_transcript_groups[tg.id] = tg

                agent_run = AgentRun(
                    id=agent_run_id,
                    name="",
                    description="",
                    transcripts=agent_run_transcripts,
                    transcript_groups=agent_run_transcript_groups,
                    metadata=metadata,
                )
                collection_agent_runs.append(agent_run)
                logger.info(
                    f"  Created agent run {agent_run_id} with {len(agent_run_transcripts)} transcripts, {len(agent_run_scores)} scores, and model: {agent_run_model or 'unknown'}"
                )
            else:
                logger.warning(f"  No transcripts created for agent_run_id: {agent_run_id}")

        return collection_agent_runs

    def _create_transcripts_from_spans(
        self, transcript_spans: List[Dict[str, Any]]
    ) -> List[Transcript]:
        """
        Create Transcript objects from spans.

        Args:
            transcript_spans: List of spans for a transcript

        Returns:
            List of Transcript objects
        """
        # Store all the chat threads and track which spans contributed to each
        chat_threads: List[List[ChatMessage]] = []
        thread_span_indices: List[List[int]] = []  # Track which spans contributed to each thread

        for span_idx, span in enumerate(transcript_spans):
            # Extract messages from this span
            span_messages = self._span_to_chat_messages(span)

            if not span_messages:
                continue

            # Find or create chat thread
            thread_index, action = self._find_or_create_chat_thread(span_messages, chat_threads)

            if action == "new":
                # Create new chat thread
                chat_threads.append(span_messages)
                thread_span_indices.append([span_idx])
                logger.debug(f"    Created new chat thread with {len(span_messages)} messages")
            elif action == "extend" and thread_index is not None:
                # Found matching thread - add new messages
                existing_thread = chat_threads[thread_index]
                new_messages = span_messages[len(existing_thread) :]
                chat_threads[thread_index].extend(new_messages)
                thread_span_indices[thread_index].append(span_idx)
                logger.info(
                    f"    Extended chat thread {thread_index} with {len(new_messages)} new messages. First new message: {new_messages[0].text[:100] if new_messages else 'N/A'}"
                )
            elif action == "skip":
                # New messages are already contained in existing thread - skip
                logger.info(
                    f"    Skipped span with {len(span_messages)} messages (already contained in thread {thread_index})"
                )

        # Create transcripts from chat threads
        transcripts: List[Transcript] = []
        if chat_threads:
            for i, chat_thread in enumerate(chat_threads):
                # Create unique transcript ID for each thread
                thread_transcript_id = str(uuid.uuid4())

                # Determine transcript_group_id for this thread based on contributing spans
                thread_transcript_group_id = None
                if thread_span_indices[i]:
                    # Use the transcript_group_id from the first span that contributed to this thread
                    first_contributing_span_idx = thread_span_indices[i][0]
                    first_contributing_span = transcript_spans[first_contributing_span_idx]
                    first_span_attrs = first_contributing_span.get("attributes", {})
                    thread_transcript_group_id = first_span_attrs.get("transcript_group_id")

                transcript = Transcript(
                    id=thread_transcript_id,
                    messages=chat_thread,
                    name=f"Chat Thread {i + 1}" if len(chat_threads) > 1 else "",
                    description="",
                    transcript_group_id=thread_transcript_group_id,
                )
                transcripts.append(transcript)
                logger.info(
                    f"    Created transcript {thread_transcript_id} with {len(chat_thread)} messages and transcript_group_id: {thread_transcript_group_id}"
                )
        else:
            logger.warning(f"    No messages extracted from {len(transcript_spans)} spans")

        return transcripts

    def _find_or_create_chat_thread(
        self, span_messages: List[ChatMessage], existing_chat_threads: List[List[ChatMessage]]
    ) -> tuple[int | None, str]:
        """
        Find the right existing chat thread to add new messages to, or indicate a new thread should be created.

        Args:
            span_messages: Messages from the current span
            existing_chat_threads: List of existing chat threads

        Returns:
            Tuple of (thread_index, action) where action is 'extend', 'skip', or 'new'
        """
        if len(span_messages) == 1:
            # Single message - create new chat thread
            return None, "new"

        # Multiple messages - try to find matching existing thread
        for i, existing_thread in enumerate(existing_chat_threads):
            # Case 1: Check if existing thread is a prefix of span_messages (extend existing)
            if len(span_messages) > len(existing_thread):
                if self.matching_thread_start(existing_thread, span_messages):
                    logger.debug(
                        f"    Found matching thread {i} for span with {len(span_messages)} messages (extend existing)"
                    )
                    return i, "extend"

            # Case 2: Check if span_messages is a prefix of existing thread (skip new)
            elif len(existing_thread) >= len(span_messages):
                if self.matching_thread_start(span_messages, existing_thread):
                    logger.debug(
                        f"    Found matching thread {i} for span with {len(span_messages)} messages (skip new - already contained)"
                    )
                    return i, "skip"

        # No match found - create new chat thread
        return None, "new"

    def matching_thread_start(
        self, existing_thread: List[ChatMessage], new_thread: List[ChatMessage]
    ) -> bool:
        """Check if the beginning of new_thread matches the existing_thread.

        This function handles tool call matching by first collecting all tool call IDs
        from both threads, then doing a matching pass that's more flexible for tool calls.

        Args:
            existing_thread: The existing chat thread to match against
            new_thread: The new chat thread to check

        Returns:
            True if the beginning of new_thread matches existing_thread, False otherwise
        """
        if not existing_thread or not new_thread:
            return False

        # First, collect all tool call IDs from both threads
        existing_thread_tool_call_ids = self._collect_all_tool_call_ids_from_thread(existing_thread)
        new_thread_tool_call_ids = self._collect_all_tool_call_ids_from_thread(new_thread)

        existing_idx = 0
        new_idx = 0

        while existing_idx < len(existing_thread) and new_idx < len(new_thread):
            existing_msg = existing_thread[existing_idx]
            new_msg = new_thread[new_idx]

            # Check if messages match directly (same role and content)
            if existing_msg.role == new_msg.role and existing_msg.text == new_msg.text:
                existing_idx += 1
                new_idx += 1
                continue

            # For tools allow just the tool_call_id to match
            if existing_msg.role == "tool" and new_msg.role == "tool":
                if (
                    existing_msg.tool_call_id
                    and new_msg.tool_call_id
                    and existing_msg.tool_call_id == new_msg.tool_call_id
                ):
                    existing_idx += 1
                    new_idx += 1
                    continue

            # if they are both assistant messages, and they both have tool_calls, if the tool_call_ids are the same, its a match
            if existing_msg.role == "assistant" and new_msg.role == "assistant":
                if existing_msg.tool_calls and new_msg.tool_calls:
                    existing_tool_call_ids = {tool_call.id for tool_call in existing_msg.tool_calls}
                    new_tool_call_ids = {tool_call.id for tool_call in new_msg.tool_calls}
                    if existing_tool_call_ids == new_tool_call_ids:
                        existing_idx += 1
                        new_idx += 1
                        continue

            # Check if existing message is a tool call we've already seen in new thread
            if (
                existing_msg.role == "tool"
                and existing_msg.tool_call_id
                and existing_msg.tool_call_id in new_thread_tool_call_ids
            ):
                existing_idx += 1
                continue

            # Check if new message is a tool call we've already seen in existing thread
            if (
                new_msg.role == "tool"
                and new_msg.tool_call_id
                and new_msg.tool_call_id in existing_thread_tool_call_ids
            ):
                new_idx += 1
                continue

            # If we get here, the messages don't match and can't be reconciled
            logger.debug(
                f"Thread matching failed: messages don't match at positions "
                f"existing_idx={existing_idx}, new_idx={new_idx}. "
                f"Existing message: role='{existing_msg.role}', text='{existing_msg.text[:50]}...' "
                f"New message: role='{new_msg.role}', text='{new_msg.text[:50]}...'"
            )
            return False

        # Return True if we've processed all of existing_thread
        result = existing_idx >= len(existing_thread)
        if not result:
            logger.debug(
                f"Thread matching failed: didn't process all of existing thread. "
                f"Processed {existing_idx}/{len(existing_thread)} existing messages, "
                f"processed {new_idx}/{len(new_thread)} new messages"
            )
        return result

    def _extract_tool_call_ids_from_message(self, msg: ChatMessage) -> set[str]:
        """Extract all tool call IDs from a message.

        Tool call IDs can come from:
        - ToolMessage.tool_call_id
        - AssistantMessage.tool_calls[].id

        Args:
            msg: The chat message to extract tool call IDs from

        Returns:
            Set of tool call IDs found in the message
        """
        tool_call_ids: set[str] = set()

        # Extract from ToolMessage
        if msg.role == "tool" and hasattr(msg, "tool_call_id") and msg.tool_call_id:
            tool_call_ids.add(msg.tool_call_id)

        # Extract from AssistantMessage tool_calls
        if msg.role == "assistant" and hasattr(msg, "tool_calls") and msg.tool_calls:
            for tool_call in msg.tool_calls:
                if tool_call.id:
                    tool_call_ids.add(tool_call.id)

        return tool_call_ids

    def _collect_all_tool_call_ids_from_thread(self, thread: List[ChatMessage]) -> set[str]:
        """Collect all tool call IDs from a thread.

        Args:
            thread: List of chat messages to extract tool call IDs from

        Returns:
            Set of all tool call IDs found in the thread
        """
        tool_call_ids: set[str] = set()

        for msg in thread:
            msg_tool_ids = self._extract_tool_call_ids_from_message(msg)
            tool_call_ids.update(msg_tool_ids)

        return tool_call_ids

    def _span_to_chat_messages(self, span: Dict[str, Any]) -> List[ChatMessage]:
        """Convert a span to a list of chat message objects."""
        span_attrs = span.get("attributes", {})
        messages: List[ChatMessage] = []

        # Debug logging
        span_id = span.get("span_id", "unknown")
        operation_name = span.get("operation_name", "unknown")
        logger.debug(
            f"Processing span {span_id} ({operation_name}) with {len(span_attrs)} attributes"
        )

        llm_request_type = span.get("llm", {}).get("request", {}).get("type", None)
        if llm_request_type == "embedding":
            logger.info(f"Skipping embedding span {span_id}")
            return []

        messages = self._extract_messages_from_span(span)

        # Debug logging
        if messages:
            logger.debug(f"Extracted {len(messages)} messages from span {span_id}")
            for i, msg in enumerate(messages):
                logger.debug(
                    f"  Message {i}: role={msg.role}, content_length={len(msg.text) if hasattr(msg, 'text') else 'N/A'}"
                )
        else:
            logger.debug(f"No messages extracted from span {span_id}")

        return messages

    def _reformat_gen_ai_attributes(self, span_attrs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Reformat gen_ai attributes from flat key-value pairs to structured dictionary.

        Example:
        Input: {
            'gen_ai.prompt.0.role': 'user',
            'gen_ai.prompt.0.content': 'Hello',
            'gen_ai.prompt.1.role': 'assistant',
            'gen_ai.prompt.1.content': 'Hi there',
            'gen_ai.completion.0.role': 'assistant',
            'gen_ai.completion.0.content': 'How can I help?',
            'gen_ai.tool_calls.0.0.id': 'call_1',
            'gen_ai.tool_calls.0.1.id': 'call_2'
        }

        Output: {
            'gen_ai': {
                'prompt': {
                    '0': {'role': 'user', 'content': 'Hello'},
                    '1': {'role': 'assistant', 'content': 'Hi there'}
                },
                'completion': {
                    '0': {'role': 'assistant', 'content': 'How can I help?'}
                },
                'tool_calls': {
                    '0': {
                        '0': {'id': 'call_1'},
                        '1': {'id': 'call_2'}
                    }
                }
            }
        }
        """
        gen_ai_data: Dict[str, Any] = {}

        for key, value in span_attrs.items():
            if not key.startswith("gen_ai."):
                continue

            # Split the key into parts: gen_ai.prompt.0.role -> ['gen_ai', 'prompt', '0', 'role']
            parts = key.split(".")
            if len(parts) < 2:  # Need at least gen_ai.something
                logger.warning(f"Invalid gen_ai attribute: {key} with value: {value}")
                continue

            # Navigate/create the nested structure
            current: Dict[str, Any] = gen_ai_data
            if "gen_ai" not in current:
                current["gen_ai"] = {}
            current = current["gen_ai"]  # type: ignore

            # Build up the nested structure
            for part in parts[1:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]  # type: ignore

            # Store the value at the final location
            current[parts[-1]] = value

        return gen_ai_data

    def _extract_messages_from_span(self, span: Dict[str, Any]) -> List[ChatMessage]:
        """Extract ChatMessage objects from structured gen_ai data."""
        messages: List[ChatMessage] = []
        span_attrs = span.get("attributes", {})
        gen_ai_data = self._reformat_gen_ai_attributes(span_attrs)

        if "gen_ai" not in gen_ai_data:
            return messages

        gen_ai = gen_ai_data["gen_ai"]

        # Process prompt messages
        if "prompt" in gen_ai:
            # Sort keys numerically to maintain proper order
            for key in sorted(
                gen_ai["prompt"].keys(), key=lambda k: (0, int(k)) if k.isdigit() else (1, k)
            ):
                # Skip keys that aren't digits
                if not key.isdigit():
                    logger.info(f"Skipping non-digit key: {key}")
                    continue

                prompt_data: dict[str, Any] = gen_ai["prompt"][key]

                message = self._create_message_from_data(prompt_data, span, f"prompt_{key}")
                if message:
                    messages.append(message)

        # Process completion messages
        if "completion" in gen_ai:
            # Sort keys numerically to maintain proper order
            for key in sorted(
                gen_ai["completion"].keys(), key=lambda k: (0, int(k)) if k.isdigit() else (1, k)
            ):
                # Skip keys that aren't digits
                if not key.isdigit():
                    logger.info(f"Skipping non-digit key: {key}")
                    continue

                completion_data: dict[str, Any] = gen_ai["completion"][key]

                message = self._create_message_from_data(
                    completion_data, span, f"completion_{key}", assume_role="assistant"
                )
                if message:
                    messages.append(message)

        return messages

    def _create_message_from_data(
        self,
        data: Dict[str, Any],
        span: Dict[str, Any],
        context: str,
        assume_role: Optional[str] = None,
    ) -> ChatMessage | None:
        """Create a ChatMessage from structured data."""
        span_id = span.get("span_id", "unknown")
        try:
            # Determine role
            if "role" in data:
                role = str(data["role"])
                if role == "developer":
                    role = "system"
            elif assume_role:
                role = assume_role
            elif "user" in data:
                role = "user"
            elif "assistant" in data:
                role = "assistant"
            elif "system" in data:
                role = "system"
            elif "developer" in data:
                role = "system"
            else:
                logger.error(
                    f"No valid role found in {context} for span {span_id}. Available keys: {list(data.keys())}"
                )
                return None

            # Build content from available fields
            content_parts: List[str] = []

            # Add reasoning if present
            if "reasoning" in data:
                reasoning = data["reasoning"]
                if isinstance(reasoning, list):
                    reasoning = "\n".join(str(item) for item in reasoning)  # type: ignore
                content_parts.append(str(reasoning))

            # Find the content key to use
            content_key = None
            possible_content_keys = [
                "content",
                "user",
                "assistant",
                "system",
                "developer",
            ]
            for possible_content_key in possible_content_keys:
                if possible_content_key in data:
                    content_key = possible_content_key
                    break

            # Extract tool calls embedded in content, return the cleaned content
            tool_calls: List[ToolCall] = []
            if content_key in data:
                try:
                    extracted_content, content_tool_calls = self._extract_tool_calls_from_content(
                        data[content_key]
                    )
                    if content_tool_calls:
                        tool_calls.extend(content_tool_calls)
                    content_parts.append(extracted_content)

                except Exception as e:
                    logger.warning(
                        f"Failed to extract tool calls from content in {context} for span {span_id}: {e}"
                    )
                    # Continue without tool calls from content

            content = "\n".join(content_parts) if content_parts else ""

            # Handle structured tool calls
            if "tool_calls" in data:
                try:
                    structured_tool_calls = self._extract_tool_calls_from_span_data(
                        data["tool_calls"]
                    )
                    if structured_tool_calls:
                        tool_calls.extend(structured_tool_calls)
                except Exception as e:
                    logger.warning(
                        f"Failed to extract structured tool calls in {context} for span {span_id}: {e}"
                    )
                    # Continue without structured tool calls

            message_data: Dict[str, Any] = {
                "role": role,
                "content": content,
            }

            if tool_calls:
                message_data["tool_calls"] = tool_calls

            logger.debug(f"Creating {context} message with data: {message_data}")
            message = parse_chat_message(message_data)
            logger.debug(f"Successfully created {context} message: role={message.role}")
            return message

        except KeyError as e:
            logger.error(
                f"Missing required field {e} in {context} for span {span_id}. Available keys: {list(data.keys())}"
            )
            return None
        except ValueError as e:
            logger.error(f"Invalid value in {context} for span {span_id}: {e}")
            return None
        except Exception as e:
            logger.error(
                f"Unexpected error creating {context} message for span {span}: {e}",
                exc_info=True,
            )
            return None

    def _extract_tool_calls_from_content(self, content: str) -> tuple[str, list[ToolCall] | None]:
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
                        content_type = item.get("type")

                        if content_type == "tool_use":
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
                            logger.info(
                                f"Extracted tool call: id={tool_call.id}, function={tool_call.function}"
                            )
                        elif content_type in ["text", "input_text"]:
                            text_content = str(item.get("text", ""))
                            filtered_content_parts.append(text_content)
                        elif content_type == "tool_result":
                            content_str = json.dumps(item.get("content", ""))
                            logger.info(f"Processing tool_result content: {content_str[:200]}...")
                            text_content, _ = self._extract_tool_calls_from_content(content_str)
                            filtered_content_parts.append(text_content)
                        else:
                            logger.warning(f"Skipping unknown content JSON type: {content_type}")

                    # Update content and tool_calls
                    if filtered_content_parts:
                        content = "\n".join(filtered_content_parts)
                    else:
                        content = ""

                    if extracted_tool_calls:
                        tool_calls = extracted_tool_calls
                        logger.info(f"Extracted {len(tool_calls)} tool calls from content")
            except json.JSONDecodeError as e:
                logger.warning(f"Content is not valid JSON: {e}, treating as regular content")

        return content, tool_calls

    def _extract_tool_calls_from_span_data(self, tool_calls_data: dict[str, Any]) -> list[ToolCall]:
        """Extract tool calls from completion message tool_calls data.

        Args:
            tool_calls_data: Dictionary containing tool call data organized by tool index

        Returns:
            List of ToolCall objects
        """
        tool_calls: list[ToolCall] = []
        logger.debug(f"Extracting tool calls from completion data: {tool_calls_data}")

        for tool_index in sorted(tool_calls_data.keys()):
            tool_data = tool_calls_data[tool_index]
            logger.debug(f"Processing tool index {tool_index}: {tool_data}")

            # Parse arguments if present
            arguments: dict[str, Any] = {}
            if "arguments" in tool_data:
                try:
                    arguments = json.loads(tool_data["arguments"])
                    logger.debug(
                        f"Successfully parsed arguments for tool {tool_index}: {arguments}"
                    )
                except json.JSONDecodeError as e:
                    logger.warning(
                        f"Failed to parse tool call arguments for tool {tool_index}: {tool_data['arguments']}, error: {e}"
                    )
                    arguments = {"raw_arguments": tool_data["arguments"]}

            tool_call = ToolCall(
                id=tool_data.get("id", ""),
                type="function",
                function=tool_data.get("name", ""),
                arguments=arguments,
            )
            tool_calls.append(tool_call)
            logger.debug(f"Created tool call: id={tool_call.id}, function={tool_call.function}")

        logger.debug(f"Extracted {len(tool_calls)} tool calls from completion data")
        return tool_calls

    def _extract_metadata_from_span_events(self, span: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract metadata from span events that were created by agent_run_metadata().

        Args:
            span: The span dictionary containing events

        Returns:
            Dictionary of metadata key-value pairs
        """
        metadata: Dict[str, Any] = {}

        for event in span.get("events", []):
            if event.get("name") == "agent_run_metadata":
                event_attrs = event.get("attributes", {})

                # Extract metadata attributes that start with "metadata."
                for key, value in event_attrs.items():
                    if key.startswith("metadata."):
                        # Remove the "metadata." prefix to get the actual key
                        metadata_key = key[len("metadata.") :]
                        metadata[metadata_key] = value

        return metadata

    def _unflatten_metadata(self, flattened_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert flattened metadata with dot notation back to nested structure.

        Args:
            flattened_metadata: Dictionary with flattened keys like "user.id", "config.model"

        Returns:
            Nested dictionary structure
        """
        unflattened: Dict[str, Any] = {}

        for key, value in flattened_metadata.items():
            parts = key.split(".")
            current = unflattened

            # Navigate/create the nested structure
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]

            # Set the value at the final location
            current[parts[-1]] = value

        return unflattened

    async def process_trace_done_with_delay(
        self,
        collection_id: str,
        user: User,
        analytics: AnalyticsClient,
        accumulation_service: TelemetryAccumulationService,
    ) -> None:
        """Process a trace-done event with a delay to allow for late-arriving spans."""
        # Wait a bit to allow for late-arriving spans
        await asyncio.sleep(5)  # 5 second delay

        # Get Redis lock for this collection
        redis_client = await get_redis_client()
        lock_key = f"{_STORE_SPANS_LOCK_PREFIX}{collection_id}"

        try:
            # Use lock to prevent concurrent processing of the same collection
            async with redis_client.lock(lock_key, blocking=False):
                # Lock acquired, process spans
                accumulated_spans = await accumulation_service.get_accumulated_spans(collection_id)

                if accumulated_spans:
                    logger.info(
                        f"Processing trace-done for collection {collection_id} with {len(accumulated_spans)} spans"
                    )
                    await self.process_completed_collection(
                        collection_id, accumulated_spans, user, analytics, accumulation_service
                    )
                else:
                    logger.warning(f"No spans found for trace-done collection {collection_id}")
        except LockError:
            logger.info(f"Collection {collection_id} is already being processed by another request")
        except Exception as e:
            logger.error(f"Error processing trace-done for collection {collection_id}: {str(e)}")
