from __future__ import annotations

import argparse
import json
import os

from docent import Docent
from docent.data_models.agent_run import AgentRun
from docent.data_models.util import clone_agent_runs_with_random_ids
from docent_core._env_util import ENV


def main(
    input_path: str,
    collection_id: str | None = None,
    collection_name: str | None = None,
    collection_description: str | None = None,
    batch_size: int = 1000,
    randomize_ids: bool = True,
):
    server_url = ENV.get("NEXT_PUBLIC_API_HOST")
    if not server_url:
        raise ValueError("NEXT_PUBLIC_API_HOST is not set")
    docent_client = Docent(server_url=server_url)

    # Determine collection_id: either use existing or create new
    if collection_name is not None:
        print(f"Creating new collection: {collection_name}")
        collection_id = docent_client.create_collection(
            name=collection_name,
            description=collection_description,
        )
        print(f"Created collection with ID: {collection_id}")
    elif collection_id is None:
        raise ValueError("Either collection_id or collection_name must be provided")

    # Read the JSON file
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    print(f"Reading agent runs from {input_path}")
    with open(input_path, "r") as f:
        agent_runs_json = json.load(f)

    # Parse JSON back into AgentRun objects
    print(f"Parsing {len(agent_runs_json)} agent runs")
    agent_runs = [AgentRun.model_validate(run_data) for run_data in agent_runs_json]

    # Optionally randomize IDs to avoid conflicts; validates consistency strictly
    if randomize_ids:
        print("Randomizing IDs for agent runs and validating consistency...")
        agent_runs = clone_agent_runs_with_random_ids(agent_runs)

    # Upload agent runs (batching handled by client)
    print(f"Uploading {len(agent_runs)} agent runs to collection {collection_id}")
    docent_client.add_agent_runs(collection_id, agent_runs, batch_size=batch_size)

    print(f"Successfully uploaded {len(agent_runs)} agent runs")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload agent runs from a JSON file to a collection. "
        "Either specify an existing collection ID or provide a name to create a new collection."
    )

    parser.add_argument(
        "input_path",
        help="Path to the JSON file containing agent runs",
    )

    # Create mutually exclusive group for collection_id vs collection_name
    collection_group = parser.add_mutually_exclusive_group(required=True)
    collection_group.add_argument(
        "--collection-id",
        help="ID of an existing collection to upload to",
    )
    collection_group.add_argument(
        "--collection-name",
        help="Name for a new collection to create and upload to",
    )

    parser.add_argument(
        "--description",
        help="Description for the new collection (only used with --collection-name)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Number of agent runs to upload per batch (default: 1000)",
    )
    parser.add_argument(
        "--randomize-ids",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Randomize all UUIDs for AgentRun, Transcript, and TranscriptGroup and "
            "validate references before upload (default: true; use --no-randomize-ids to disable)"
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    main(
        input_path=args.input_path,
        collection_id=args.collection_id,
        collection_name=args.collection_name,
        collection_description=args.description,
        batch_size=args.batch_size,
        randomize_ids=args.randomize_ids,
    )
