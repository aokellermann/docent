import json
from pathlib import Path
from typing import Any, List, Tuple, cast
from uuid import uuid4

from docent.data_models.agent_run import AgentRun


async def import_agent_runs_from_json(file_path: Path) -> Tuple[List[AgentRun], dict[str, Any]]:
    """Import agent runs from a JSON file containing a list of agent run dictionaries.

    Args:
        file_path: Path to the JSON file containing a list of agent run dictionaries

    Returns:
        tuple: (agent_runs, file_info) where file_info contains metadata about the file

    Raises:
        ValueError: If the JSON structure is invalid or agent run validation fails
        FileNotFoundError: If the file doesn't exist
        json.JSONDecodeError: If the file contains invalid JSON
    """
    with open(file_path, "r") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(f"Expected JSON file to contain a list, got {type(data).__name__}")

    agent_runs = []
    for i, agent_run_dict in enumerate(data):
        try:
            # Replace agent run ID with new UUID
            agent_run_dict["id"]
            new_agent_run_id = str(uuid4())
            agent_run_dict["id"] = new_agent_run_id

            # Normalize transcripts/transcript_groups to lists if provided as dicts
            transcripts_raw = agent_run_dict.get("transcripts", [])
            if isinstance(transcripts_raw, dict):
                transcripts_list = list(cast(dict[str, Any], transcripts_raw).values())
            else:
                transcripts_list = cast(List[dict[str, Any]], transcripts_raw)

            transcript_groups_raw = agent_run_dict.get("transcript_groups", [])
            if isinstance(transcript_groups_raw, dict):
                transcript_groups_list = list(cast(dict[str, Any], transcript_groups_raw).values())
            else:
                transcript_groups_list = cast(List[dict[str, Any]], transcript_groups_raw)

            # Create mapping for transcript IDs and replace them in place
            transcript_id_mapping: dict[str, str] = {}
            for transcript in transcripts_list:
                old_transcript_id = transcript.get("id")
                if old_transcript_id is None:
                    raise ValueError("Transcript missing 'id'")
                new_transcript_id = str(uuid4())
                transcript["id"] = new_transcript_id
                transcript_id_mapping[str(old_transcript_id)] = new_transcript_id

            # Create mapping for transcript group IDs and replace them in place
            transcript_group_id_mapping: dict[str, str] = {}
            for transcript_group in transcript_groups_list:
                old_tg_id = transcript_group.get("id")
                if old_tg_id is None:
                    raise ValueError("TranscriptGroup missing 'id'")
                new_tg_id = str(uuid4())
                transcript_group["id"] = new_tg_id
                transcript_group_id_mapping[str(old_tg_id)] = new_tg_id

                # Update agent_run_id reference
                transcript_group["agent_run_id"] = new_agent_run_id

            # Update parent_transcript_group_id references on transcript groups
            for tg in transcript_groups_list:
                old_parent_id = tg.get("parent_transcript_group_id")
                if old_parent_id is not None:
                    old_parent_id_str = str(old_parent_id)
                    if old_parent_id_str in transcript_group_id_mapping:
                        tg["parent_transcript_group_id"] = transcript_group_id_mapping[
                            old_parent_id_str
                        ]

            # Update transcript_group_id references on transcripts
            for transcript in transcripts_list:
                old_tg_id = transcript.get("transcript_group_id")
                if old_tg_id is not None:
                    old_tg_id_str = str(old_tg_id)
                    if old_tg_id_str in transcript_group_id_mapping:
                        transcript["transcript_group_id"] = transcript_group_id_mapping[
                            old_tg_id_str
                        ]

            # Persist normalized lists back to payload
            agent_run_dict["transcripts"] = transcripts_list
            agent_run_dict["transcript_groups"] = transcript_groups_list

            agent_run = AgentRun.model_validate(agent_run_dict)
            agent_runs.append(agent_run)
        except Exception as e:
            raise ValueError(f"Failed to validate agent run at index {i}: {e}")

    file_info = {
        "filename": file_path.name,
        "total_agent_runs": len(agent_runs),
    }

    return agent_runs, file_info
