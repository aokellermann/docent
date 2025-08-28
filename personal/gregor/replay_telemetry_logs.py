#!/usr/bin/env python3
"""
Script to replay telemetry logs for testing.

This script takes a set of telemetry log IDs and an API key, retrieves the stored
telemetry data, and processes it through the same shared functions that the trace
endpoint uses. This allows for testing the trace processing logic without needing
to send actual HTTP requests.

The script can also process trace-done events to signal that a trace is complete,
either as part of replaying logs or independently.

Usage:
    python replay_telemetry_logs.py --api-key dk_xxx --log-ids id1,id2,id3
    python replay_telemetry_logs.py --api-key dk_xxx --log-ids id1,id2,id3 --dry-run
    python replay_telemetry_logs.py --api-key dk_xxx --trace-done-only collection_123
    python replay_telemetry_logs.py --api-key dk_xxx --collection-id collection_123 --delete-collection
    python replay_telemetry_logs.py --api-key dk_xxx --log-ids id1,id2,id3 --clean-accumulation
"""

import argparse
import asyncio
import logging
import os
import sys
from typing import List

from sqlalchemy import update

from docent._log_util import get_logger
from docent_core.docent.db.schemas.auth_models import User
from docent_core.docent.db.schemas.tables import SQLATelemetryLog
from docent_core.docent.services.monoservice import MonoService
from docent_core.docent.services.telemetry import TelemetryService
from docent_core.docent.services.telemetry_accumulation import TelemetryAccumulationService

logger = get_logger(__name__)

logging.getLogger("docent_core.docent.services.telemetry").setLevel(logging.DEBUG)


async def delete_collection_if_exists(
    collection_id: str,
    user: User,
    mono_svc: MonoService,
    accumulation_service: TelemetryAccumulationService | None = None,
) -> None:
    """
    Delete a collection if it exists and the user has permission.

    Args:
        collection_id: The collection ID to delete
        user: The authenticated user
        mono_svc: The database service
        accumulation_service: Optional accumulation service to clean up accumulation data
    """
    try:
        # Check if collection exists
        if await mono_svc.collection_exists(collection_id):
            logger.info(f"Deleting existing collection: {collection_id}")

            # Clean up accumulation data first if service is provided
            if accumulation_service:
                logger.info(f"Cleaning up accumulation data for collection: {collection_id}")
                await accumulation_service.cleanup_collection_data(collection_id)

            # Delete the collection
            await mono_svc.delete_collection(collection_id)
            logger.info(f"Successfully deleted collection: {collection_id}")
        else:
            logger.info(f"Collection {collection_id} does not exist, nothing to delete")

    except Exception as e:
        logger.error(f"Error deleting collection {collection_id}: {e}")
        raise


async def replay_telemetry_logs(
    telemetry_log_ids: List[str],
    api_key: str,
    skip_trace_done: bool = False,
    collection_id: str | None = None,
    auto_delete_collections: bool = False,
    skip_collection_deletion: bool = False,
    clean_accumulation: bool = False,
) -> None:
    """
    Replay telemetry logs by retrieving them from the database and processing them.

    Args:
        telemetry_log_ids: List of telemetry log IDs to replay
        api_key: API key for authentication
        skip_trace_done: If True, skip calling the trace-done endpoint at the end
        collection_id: The collection ID (optional, for specific collection processing)
        auto_delete_collections: If True, automatically delete existing collections without prompting
        skip_collection_deletion: If True, skip collection deletion entirely
        clean_accumulation: If True, clean accumulation data for existing collections before processing
    """
    # Initialize database service
    mono_svc = await MonoService.init()

    # Authenticate user with API key
    user = await mono_svc.get_user_by_api_key(api_key)
    if not user:
        logger.error("Invalid API key")
        sys.exit(1)

    logger.info(f"Authenticated as user: {user.email} ({user.id})")

    # Initialize telemetry services
    logger.info("Initializing telemetry services...")
    async with mono_svc.db.session() as session:
        logger.info("Database session created")
        telemetry_svc = TelemetryService(session, mono_svc)
        accumulation_service = TelemetryAccumulationService(session)
        logger.info("Telemetry services initialized")

        # Extract collection IDs from telemetry logs to check if collections exist
        logger.info(
            f"Starting to extract collection IDs from {len(telemetry_log_ids)} telemetry logs..."
        )
        collection_ids_from_logs: set[str] = set()

        for i, log_id in enumerate(telemetry_log_ids, 1):
            logger.info(f"Reading telemetry log {i}/{len(telemetry_log_ids)}: {log_id}")
            try:
                telemetry_log = await telemetry_svc.get_telemetry_log(log_id)
                if not telemetry_log:
                    logger.warning(f"Telemetry log {log_id} not found, skipping")
                    continue

                # Extract collection IDs from the trace data
                trace_data = telemetry_log.json_data

                if "collection_id" in trace_data:
                    collection_ids_from_logs.add(trace_data["collection_id"])
                else:
                    spans = await telemetry_svc.extract_spans(trace_data)

                    # Extract unique collection IDs and names from spans
                    collection_ids, _ = telemetry_svc.extract_collection_info_from_spans(spans)
                    collection_ids_from_logs.update(collection_ids)

            except Exception as e:
                logger.error(
                    f"Error extracting collection IDs from telemetry log {log_id}: {str(e)}"
                )
                continue
        logger.info(f"Collection IDs found in telemetry logs: {collection_ids_from_logs}")

        # Check if any collections exist and ask user if they want to delete
        logger.info("Checking which collections exist...")
        existing_collections: list[str] = []
        for coll_id in collection_ids_from_logs:
            logger.info(f"Checking if collection exists: {coll_id}")
            if await mono_svc.collection_exists(coll_id):
                logger.info(f"Collection {coll_id} exists")
                existing_collections.append(coll_id)
            else:
                logger.info(f"Collection {coll_id} does not exist")

        logger.info(
            f"Found {len(existing_collections)} existing collections: {existing_collections}"
        )

        # Clean accumulation data if requested
        if clean_accumulation and existing_collections:
            logger.info("Cleaning accumulation data for existing collections...")
            for coll_id in existing_collections:
                try:
                    logger.info(f"Cleaning accumulation data for collection: {coll_id}")
                    await accumulation_service.cleanup_collection_data(coll_id)
                    logger.info(f"Successfully cleaned accumulation data for collection: {coll_id}")
                except Exception as e:
                    logger.error(f"Error cleaning accumulation data for collection {coll_id}: {e}")
                    # Continue with other collections even if one fails
            logger.info("Finished cleaning accumulation data")

        if existing_collections:
            logger.info(f"Found existing collections: {existing_collections}")

            # Determine whether to delete collections
            should_delete = False

            if skip_collection_deletion:
                logger.info("Skipping collection deletion due to --skip-collection-deletion flag")
                should_delete = False
            elif auto_delete_collections:
                logger.info(
                    "Automatically deleting collections due to --auto-delete-collections flag"
                )
                should_delete = True
            else:
                logger.info("About to prompt user for deletion decision...")
                # Ask user if they want to delete
                response = input(
                    f"Found existing collections: {existing_collections}. Delete them? (y/N): "
                )
                logger.info(f"User response: '{response}'")
                should_delete = response.lower() in ["y", "yes"]

            if should_delete:
                # Temporarily set collection_id to null for telemetry logs we're processing
                # to prevent them from being deleted when we delete the collection
                for log_id in telemetry_log_ids:
                    try:
                        await session.execute(
                            update(SQLATelemetryLog)
                            .where(SQLATelemetryLog.id == log_id)
                            .values(collection_id=None)
                        )
                    except Exception as e:
                        logger.warning(f"Could not update telemetry log {log_id}: {e}")

                # Commit the changes to persist the collection_id updates
                await session.commit()
                logger.info(
                    "Temporarily set collection_id to null for telemetry logs and committed changes"
                )

                # Delete the existing collections
                for coll_id in existing_collections:
                    await delete_collection_if_exists(coll_id, user, mono_svc)
            else:
                logger.info("Skipping collection deletion")
        else:
            logger.info("No existing collections found in telemetry logs")

        # Track collection IDs that we process
        processed_collections: set[str] = set()

        # Process each telemetry log
        for i, log_id in enumerate(telemetry_log_ids, 1):
            logger.info(f"Processing telemetry log {i}/{len(telemetry_log_ids)}: {log_id}")

            try:
                # Retrieve telemetry log from database
                telemetry_log = await telemetry_svc.get_telemetry_log(log_id)
                if not telemetry_log:
                    logger.error(f"Telemetry log {log_id} not found")
                    continue

                # Extract data from the stored JSON
                log_data = telemetry_log.json_data
                log_type = telemetry_log.type
                logger.info(f"Processing telemetry log {log_id} of type: {log_type}")

                # Process based on telemetry log type
                if log_type == "traces":
                    # Handle trace data (spans)
                    logger.info(
                        f"Retrieved trace data with {len(log_data.get('resource_spans', []))} resource spans"
                    )
                    spans = await telemetry_svc.extract_spans(log_data)
                    logger.info(f"Extracted {len(spans)} spans from telemetry log {log_id}")

                    # Extract collection IDs and names from spans
                    collection_ids, collection_names = (
                        telemetry_svc.extract_collection_info_from_spans(spans)
                    )

                    # Ensure collections exist before accumulating spans (like the REST endpoints do)
                    await telemetry_svc.ensure_collections_exist(
                        collection_ids, collection_names, user
                    )

                    # Use the accumulate_spans function to handle grouping and storage
                    await telemetry_svc.accumulate_spans(spans, user.id, accumulation_service)

                    # Track processed collections
                    for collection_id in collection_ids:
                        processed_collections.add(collection_id)

                elif log_type == "scores":
                    # Handle score data
                    collection_id = log_data.get("collection_id")
                    agent_run_id = log_data.get("agent_run_id")
                    score_name = log_data.get("score_name")
                    score_value = log_data.get("score_value")
                    timestamp = log_data.get("timestamp")

                    # Ensure collection exists if we have a collection_id
                    if collection_id:
                        await telemetry_svc.ensure_collection_exists(collection_id, user)

                    if all(
                        [
                            collection_id,
                            agent_run_id,
                            score_name,
                            score_value is not None,
                            timestamp,
                        ]
                    ):
                        # Type checker doesn't understand that all() ensures non-None values
                        assert collection_id is not None
                        assert agent_run_id is not None
                        assert score_name is not None
                        assert timestamp is not None

                        await accumulation_service.add_score(
                            collection_id=collection_id,
                            agent_run_id=agent_run_id,
                            score_name=score_name,
                            score_value=score_value,
                            timestamp=timestamp,
                            user_id=user.id,
                        )
                        processed_collections.add(collection_id)
                        logger.info(
                            f"Added score {score_name}={score_value} for agent run {agent_run_id}"
                        )
                    else:
                        logger.warning(
                            f"Missing required fields for score in telemetry log {log_id}"
                        )

                elif log_type == "metadata":
                    # Handle agent run metadata
                    collection_id = log_data.get("collection_id")
                    agent_run_id = log_data.get("agent_run_id")
                    metadata = log_data.get("metadata")
                    timestamp = log_data.get("timestamp")

                    # Ensure collection exists if we have a collection_id
                    if collection_id:
                        await telemetry_svc.ensure_collection_exists(collection_id, user)

                    if all([collection_id, agent_run_id, metadata, timestamp]):
                        # Type checker doesn't understand that all() ensures non-None values
                        assert collection_id is not None
                        assert agent_run_id is not None
                        assert metadata is not None
                        assert timestamp is not None

                        await accumulation_service.add_agent_run_metadata(
                            collection_id=collection_id,
                            agent_run_id=agent_run_id,
                            metadata=metadata,
                            timestamp=timestamp,
                            user_id=user.id,
                        )
                        processed_collections.add(collection_id)
                        logger.info(f"Added metadata for agent run {agent_run_id}")
                    else:
                        logger.warning(
                            f"Missing required fields for metadata in telemetry log {log_id}"
                        )

                elif log_type == "transcript-metadata":
                    # Handle transcript metadata
                    collection_id = log_data.get("collection_id")
                    transcript_id = log_data.get("transcript_id")
                    name = log_data.get("name")
                    description = log_data.get("description")
                    transcript_group_id = log_data.get("transcript_group_id")
                    metadata = log_data.get("metadata")
                    timestamp = log_data.get("timestamp")

                    # Ensure collection exists if we have a collection_id
                    if collection_id:
                        await telemetry_svc.ensure_collection_exists(collection_id, user)

                    if all([collection_id, transcript_id, timestamp]):
                        await accumulation_service.add_transcript_metadata(
                            collection_id=collection_id,
                            transcript_id=transcript_id,
                            name=name,
                            description=description,
                            transcript_group_id=transcript_group_id,
                            metadata=metadata,
                            timestamp=timestamp,
                            user_id=user.id,
                        )
                        processed_collections.add(collection_id)
                        logger.info(f"Added transcript metadata for transcript {transcript_id}")
                    else:
                        logger.warning(
                            f"Missing required fields for transcript metadata in telemetry log {log_id}"
                        )

                elif log_type == "transcript-group-metadata":
                    # Handle transcript group metadata
                    collection_id = log_data.get("collection_id")
                    agent_run_id = log_data.get("agent_run_id")
                    transcript_group_id = log_data.get("transcript_group_id")
                    name = log_data.get("name")
                    description = log_data.get("description")
                    parent_transcript_group_id = log_data.get("parent_transcript_group_id")
                    metadata = log_data.get("metadata")
                    timestamp = log_data.get("timestamp")

                    # Ensure collection exists if we have a collection_id
                    if collection_id:
                        await telemetry_svc.ensure_collection_exists(collection_id, user)

                    if all([collection_id, agent_run_id, transcript_group_id, timestamp]):
                        await accumulation_service.add_transcript_group_metadata(
                            collection_id=collection_id,
                            agent_run_id=agent_run_id,
                            transcript_group_id=transcript_group_id,
                            name=name,
                            description=description,
                            parent_transcript_group_id=parent_transcript_group_id,
                            metadata=metadata,
                            timestamp=timestamp,
                            user_id=user.id,
                        )
                        processed_collections.add(collection_id)
                        logger.info(
                            f"Added transcript group metadata for group {transcript_group_id}"
                        )
                    else:
                        logger.warning(
                            f"Missing required fields for transcript group metadata in telemetry log {log_id}"
                        )

                elif log_type == "trace-done":
                    # Handle trace-done events (just log for now)
                    collection_id = log_data.get("collection_id")
                    if collection_id:
                        processed_collections.add(collection_id)
                        logger.info(f"Processed trace-done event for collection {collection_id}")
                    else:
                        logger.warning(
                            f"Missing collection_id for trace-done in telemetry log {log_id}"
                        )

                else:
                    logger.warning(f"Unknown telemetry log type: {log_type} for log {log_id}")
                    continue

                logger.info(f"Successfully processed telemetry log {log_id}")

            except Exception as e:
                logger.error(f"Error processing telemetry log {log_id}: {str(e)}", exc_info=True)
                raise

        # Simulate running the background processing jobs that would be triggered by REST endpoints
        if processed_collections:
            logger.info(
                f"Processed {len(processed_collections)} collections: {list(processed_collections)}"
            )
            logger.info("Simulating background processing jobs...")

            for collection_id in processed_collections:
                logger.info(f"Processing agent runs for collection: {collection_id}")
                await telemetry_svc.process_agent_runs_for_collection(collection_id, user)
        else:
            logger.info("No collections were processed")


async def process_collection_agent_runs(collection_id: str, api_key: str) -> None:
    """
    Process agent runs for a specific collection without replaying telemetry logs.

    Args:
        collection_id: The collection ID to process agent runs for
        api_key: API key for authentication
    """
    # Initialize database service
    mono_svc = await MonoService.init()

    # Authenticate user with API key
    user = await mono_svc.get_user_by_api_key(api_key)
    if not user:
        logger.error("Invalid API key")
        sys.exit(1)

    logger.info(f"Authenticated as user: {user.email} ({user.id})")

    # Check if collection exists
    if not await mono_svc.collection_exists(collection_id):
        logger.error(f"Collection {collection_id} does not exist")
        sys.exit(1)

    # Check if user has permission to access the collection
    from docent_core.docent.db.schemas.auth_models import Permission, ResourceType

    has_permission = await mono_svc.has_permission(
        user=user,
        resource_type=ResourceType.COLLECTION,
        resource_id=collection_id,
        permission=Permission.WRITE,
    )
    if not has_permission:
        logger.error(f"User {user.id} does not have write permission on collection {collection_id}")
        sys.exit(1)

    # Initialize telemetry service
    async with mono_svc.db.session() as session:
        telemetry_svc = TelemetryService(session, mono_svc)

        logger.info(f"Processing agent runs for collection: {collection_id}")
        await telemetry_svc.process_agent_runs_for_collection(collection_id, user)
        logger.info(f"Successfully processed agent runs for collection: {collection_id}")


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Replay telemetry logs for testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Replay specific telemetry logs (will ask if collections exist)
    python replay_telemetry_logs.py --api-key dk_xxx --log-ids id1,id2,id3

    # Replay logs from a specific collection (will ask if collection exists)
    python replay_telemetry_logs.py --api-key dk_xxx --collection-id collection_123

    # Just process agent runs for a collection (without replaying telemetry logs)
    python replay_telemetry_logs.py --api-key dk_xxx --process-collection collection_123

    # Skip calling trace-done endpoint (useful for testing)
    python replay_telemetry_logs.py --api-key dk_xxx --log-ids id1,id2,id3 --skip-trace-done

    # Clean accumulation data before processing (useful for testing with existing collections)
    python replay_telemetry_logs.py --api-key dk_xxx --log-ids id1,id2,id3 --clean-accumulation
        """,
    )

    parser.add_argument(
        "--api-key",
        default=os.getenv("DOCENT_API_KEY"),
        help="API key for authentication (starts with dk_). Defaults to DOCENT_API_KEY environment variable",
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--log-ids",
        default="log_ids.txt",
        help="Comma-separated list of telemetry log IDs to replay, or path to file containing one ID per line (default: log_ids.txt)",
    )
    group.add_argument(
        "--collection-id",
        help="Collection ID to replay all telemetry logs for",
    )
    group.add_argument(
        "--process-collection",
        help="Collection ID to just process agent runs for (without replaying telemetry logs)",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of telemetry logs to process (default: 100)",
    )

    parser.add_argument(
        "--skip-trace-done",
        action="store_true",
        help="Skip calling the trace-done endpoint at the end",
    )

    parser.add_argument(
        "--auto-delete-collections",
        action="store_true",
        help="Automatically delete existing collections without prompting",
    )

    parser.add_argument(
        "--skip-collection-deletion",
        action="store_true",
        help="Skip collection deletion entirely (keep existing collections)",
    )

    parser.add_argument(
        "--clean-accumulation",
        action="store_true",
        help="Clean accumulation data for collections before processing telemetry logs",
    )

    args = parser.parse_args()

    # Validate API key
    if not args.api_key:
        logger.error(
            "API key is required. Please provide --api-key or set DOCENT_API_KEY environment variable"
        )
        sys.exit(1)

    if not args.api_key.startswith("dk_"):
        logger.error("API key must start with 'dk_'")
        sys.exit(1)

        # Determine which telemetry logs to process
    telemetry_log_ids = []

    if args.process_collection:
        # Just process agent runs for the collection without replaying telemetry logs
        logger.info(f"Will process agent runs for collection: {args.process_collection}")
        try:
            asyncio.run(process_collection_agent_runs(args.process_collection, args.api_key))
            logger.info("Collection agent run processing completed successfully")
        except KeyboardInterrupt:
            logger.info("Collection agent run processing interrupted by user")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Collection agent run processing failed: {str(e)}", exc_info=True)
            sys.exit(1)
    elif args.collection_id:
        # Get telemetry logs for the collection
        async def get_collection_logs():
            mono_svc = await MonoService.init()
            async with mono_svc.db.session() as session:
                telemetry_svc = TelemetryService(session, mono_svc)
                logs = await telemetry_svc.get_telemetry_logs_by_collection(
                    args.collection_id, args.limit
                )
                return [log.id for log in logs]

        telemetry_log_ids = asyncio.run(get_collection_logs())
        if not telemetry_log_ids:
            logger.error(f"No telemetry logs found for collection {args.collection_id}")
            sys.exit(1)
    else:
        # Use log_ids (defaults to log_ids.txt)
        # Check if log_ids is a file path
        if os.path.isfile(args.log_ids):
            # Read log IDs from file (one per line)
            with open(args.log_ids, "r") as f:
                telemetry_log_ids = [line.strip() for line in f if line.strip()]
            logger.info(f"Read {len(telemetry_log_ids)} log IDs from file: {args.log_ids}")
        else:
            # Parse as comma-separated list
            telemetry_log_ids = [log_id.strip() for log_id in args.log_ids.split(",")]

        if not telemetry_log_ids:
            logger.error(f"No log IDs found in {args.log_ids}")
            sys.exit(1)

    if not args.process_collection:
        logger.info(f"Will process {len(telemetry_log_ids)} telemetry logs")

        # Run the replay
        try:
            asyncio.run(
                replay_telemetry_logs(
                    telemetry_log_ids,
                    args.api_key,
                    args.skip_trace_done,
                    args.collection_id,
                    args.auto_delete_collections,
                    args.skip_collection_deletion,
                    args.clean_accumulation,
                )
            )
            logger.info("Telemetry log replay completed successfully")
        except KeyboardInterrupt:
            logger.info("Telemetry log replay interrupted by user")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Telemetry log replay failed: {str(e)}", exc_info=True)
            sys.exit(1)


if __name__ == "__main__":
    main()
