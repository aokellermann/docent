from __future__ import annotations

from typing import Dict, Iterable, List, TypeVar
from uuid import uuid4

from pydantic import BaseModel

from docent.data_models.agent_run import AgentRun

T = TypeVar("T", bound=BaseModel)


def _deep_copy_model(model: T) -> T:
    """Create a deep copy of a Pydantic v2 model.

    Using `model_copy(deep=True)` ensures nested models are fully copied and
    mutations do not affect the original instance.
    """
    return model.model_copy(deep=True)


def clone_agent_run_with_random_ids(agent_run: AgentRun) -> AgentRun:
    """Clone an `AgentRun`, randomizing all IDs and fixing internal references.

    The following transformations are performed on the cloned instance:
    - Assign a new `AgentRun.id`.
    - Assign new `Transcript.id` values and update any references to them (none today).
    - Assign new `TranscriptGroup.id` values.
    - Update `Transcript.transcript_group_id` to the new group IDs where applicable.
    - Update `TranscriptGroup.agent_run_id` to the new `AgentRun.id`.
    - Update `TranscriptGroup.parent_transcript_group_id` to the new group IDs where applicable.

    Notes:
    - If a `parent_transcript_group_id` or `transcript_group_id` references a group id that
      is not present in the cloned run, the reference is left unchanged (mirrors importer behavior).

    Args:
        agent_run: The source `AgentRun` to clone.

    Returns:
        A new, independent `AgentRun` instance with randomized identifiers and consistent references.
    """
    # Validate source integrity before cloning
    #  - No duplicate transcript or group IDs
    #  - All transcript.group references exist if set
    #  - All group.parent references exist if set
    #  - All group.agent_run_id match the source run id
    src_transcript_ids = [str(t.id) for t in agent_run.transcripts]
    if len(src_transcript_ids) != len(set(src_transcript_ids)):
        raise ValueError("Duplicate transcript ids detected in source AgentRun")

    src_group_ids = [str(g.id) for g in agent_run.transcript_groups]
    if len(src_group_ids) != len(set(src_group_ids)):
        raise ValueError("Duplicate transcript group ids detected in source AgentRun")

    src_group_id_set = set(src_group_ids)
    for t in agent_run.transcripts:
        if t.transcript_group_id is not None and str(t.transcript_group_id) not in src_group_id_set:
            raise ValueError(
                f"Transcript {t.id} references missing transcript_group_id {t.transcript_group_id}"
            )

    for g in agent_run.transcript_groups:
        if (
            g.parent_transcript_group_id is not None
            and str(g.parent_transcript_group_id) not in src_group_id_set
        ):
            raise ValueError(
                f"TranscriptGroup {g.id} references missing parent_transcript_group_id {g.parent_transcript_group_id}"
            )
        if str(g.agent_run_id) != str(agent_run.id):
            raise ValueError(
                f"TranscriptGroup {g.id} has agent_run_id {g.agent_run_id} which does not match AgentRun.id {agent_run.id}"
            )

    # Deep copy first so we never mutate the caller's instance
    new_run = _deep_copy_model(agent_run)

    # 1) Randomize AgentRun ID
    new_agent_run_id = str(uuid4())
    old_to_new_transcript_id: Dict[str, str] = {}
    old_to_new_group_id: Dict[str, str] = {}

    # 2) Pre-compute new IDs for transcripts and transcript groups without mutating yet
    for transcript in new_run.transcripts:
        old_to_new_transcript_id[str(transcript.id)] = str(uuid4())

    for group in new_run.transcript_groups:
        old_to_new_group_id[str(group.id)] = str(uuid4())

    # 3) Mutate transcript groups: set new id, set agent_run_id, remap parents
    for group in new_run.transcript_groups:
        old_group_id = str(group.id)

        # Assign new group id
        group.id = old_to_new_group_id.get(old_group_id, str(uuid4()))

        # Ensure group points to the new agent run id
        group.agent_run_id = new_agent_run_id

        # Remap parent id; raise if unknown
        if group.parent_transcript_group_id is not None:
            old_parent_id = str(group.parent_transcript_group_id)
            if old_parent_id not in old_to_new_group_id:
                raise ValueError(
                    f"TranscriptGroup {old_group_id} parent_transcript_group_id {old_parent_id} not found in this AgentRun"
                )
            group.parent_transcript_group_id = old_to_new_group_id[old_parent_id]

    # 4) Mutate transcripts: set new id, remap transcript_group_id
    for transcript in new_run.transcripts:
        old_transcript_id = str(transcript.id)

        # Assign new transcript id
        transcript.id = old_to_new_transcript_id.get(old_transcript_id, str(uuid4()))

        # Remap group reference; raise if unknown
        if transcript.transcript_group_id is not None:
            old_group_id_ref = str(transcript.transcript_group_id)
            if old_group_id_ref not in old_to_new_group_id:
                raise ValueError(
                    f"Transcript {old_transcript_id} references transcript_group_id {old_group_id_ref} not found in this AgentRun"
                )
            transcript.transcript_group_id = old_to_new_group_id[old_group_id_ref]

    # 5) Finally set the new run id
    new_run.id = new_agent_run_id

    # Post-validate integrity on the cloned run
    new_group_ids = [str(g.id) for g in new_run.transcript_groups]
    if len(new_group_ids) != len(set(new_group_ids)):
        raise ValueError("Duplicate transcript group ids detected after cloning")
    new_group_id_set = set(new_group_ids)

    new_transcript_ids = [str(t.id) for t in new_run.transcripts]
    if len(new_transcript_ids) != len(set(new_transcript_ids)):
        raise ValueError("Duplicate transcript ids detected after cloning")

    for t in new_run.transcripts:
        if t.transcript_group_id is not None and str(t.transcript_group_id) not in new_group_id_set:
            raise ValueError(
                f"Transcript {t.id} references missing transcript_group_id {t.transcript_group_id} after cloning"
            )

    for g in new_run.transcript_groups:
        if (
            g.parent_transcript_group_id is not None
            and str(g.parent_transcript_group_id) not in new_group_id_set
        ):
            raise ValueError(
                f"TranscriptGroup {g.id} references missing parent_transcript_group_id {g.parent_transcript_group_id} after cloning"
            )
        if str(g.agent_run_id) != str(new_run.id):
            raise ValueError(
                f"TranscriptGroup {g.id} has agent_run_id {g.agent_run_id} which does not match cloned AgentRun.id {new_run.id}"
            )

    return new_run


def clone_agent_runs_with_random_ids(agent_runs: Iterable[AgentRun]) -> List[AgentRun]:
    """Clone a sequence of `AgentRun` objects with randomized IDs.

    Args:
        agent_runs: Iterable of `AgentRun` instances to clone.

    Returns:
        A list of cloned `AgentRun` instances with fresh IDs and consistent references.
    """
    return [clone_agent_run_with_random_ids(ar) for ar in agent_runs]
