import anyio
from tqdm.auto import tqdm

from docent._llm_util.llm_svc import BaseLLMService
from docent._log_util import get_logger
from docent.data_models.agent_run import AgentRun
from docent.judges import (
    JudgeResult,
    JudgeResultCompletionCallback,
    Rubric,
)
from docent.judges.impl import build_judge

logger = get_logger(__name__)


async def run_rubric(
    agent_runs: list[AgentRun],
    rubric: Rubric,
    llm_svc: BaseLLMService,
    callback: JudgeResultCompletionCallback | None = None,
    *,
    n_rollouts_per_input: int | list[int] = 1,
    show_progress: bool = True,
) -> list[JudgeResult | None]:
    if not agent_runs:
        raise ValueError("agent_runs must be a non-empty sequence")
    if rubric.n_rollouts_per_input <= 0:
        raise ValueError("rubric.n_rollouts_per_input must be greater than 0")

    # Normalize n_rollouts_per_input to a list
    if isinstance(n_rollouts_per_input, int):
        if n_rollouts_per_input < 0:
            raise ValueError("n_rollouts_per_input must be non-negative")
        rollouts_per_run = [n_rollouts_per_input] * len(agent_runs)
    else:
        rollouts_per_run = n_rollouts_per_input
        if len(rollouts_per_run) != len(agent_runs):
            raise ValueError("n_rollouts_per_input list must match agent_runs length")
        if any(n < 0 for n in rollouts_per_run):
            raise ValueError("All values in n_rollouts_per_input must be non-negative")

    judge = build_judge(rubric, llm_svc)

    total_rollouts = sum(rollouts_per_run)
    logger.info(
        "Running rubric %s version %s against %d agent runs with %d total rollouts",
        rubric.id,
        rubric.version,
        len(agent_runs),
        total_rollouts,
    )

    agent_results: list[list[JudgeResult | None]] = [[] for _ in agent_runs]
    progress_bar = tqdm(
        total=total_rollouts,
        desc=f"Rubric {rubric.id}",
        disable=not show_progress,
    )

    async def _run_single_judge(index: int, agent_run: AgentRun):
        rollout_results: list[JudgeResult | None] = []
        for _ in range(rollouts_per_run[index]):
            result = await judge(agent_run)
            rollout_results.append(result)
            progress_bar.update()

        agent_results[index] = rollout_results

        if callback is not None:
            # Filter out None results for the callback
            valid_results = [r for r in rollout_results if r is not None]
            await callback(index, valid_results if valid_results else None)

    try:
        async with anyio.create_task_group() as tg:
            for index, agent_run in enumerate(agent_runs):
                tg.start_soon(_run_single_judge, index, agent_run)
    finally:
        progress_bar.close()

    flattened_results = [result for rollouts in agent_results for result in rollouts]
    successful = sum(result is not None for result in flattened_results)
    logger.info(
        "Finished rubric %s: produced %d/%d judge results",
        rubric.id,
        successful,
        len(flattened_results),
    )

    return flattened_results
