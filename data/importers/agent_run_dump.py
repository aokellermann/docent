import json
from pathlib import Path
from typing import Any, List, Tuple

from docent.data_models.agent_run import AgentRun
from docent.data_models.util import clone_agent_runs_with_random_ids


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

    validated_runs: List[AgentRun] = []
    for i, agent_run_dict in enumerate(data):
        try:
            # Rely on AgentRun validators to normalize dicts to lists where needed
            agent_run = AgentRun.model_validate(agent_run_dict)
            validated_runs.append(agent_run)
        except Exception as e:
            raise ValueError(f"Failed to validate agent run at index {i}: {e}")

    # Randomize IDs and strictly validate internal references using shared utility
    agent_runs = clone_agent_runs_with_random_ids(validated_runs)

    file_info = {
        "filename": file_path.name,
        "total_agent_runs": len(agent_runs),
    }

    return agent_runs, file_info
