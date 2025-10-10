import time
from typing import Literal

import anyio
from tqdm.auto import tqdm

from docent._log_util import get_logger
from docent.data_models.agent_run import AgentRun
from docent.judges import (
    JudgeResult,
    JudgeResultCompletionCallback,
    MajorityVotingJudge,
    MultiReflectionJudge,
    Rubric,
)
from docent_core.docent.services.llms import LLMService

logger = get_logger(__name__)


async def evaluate_rubric(
    agent_runs: list[AgentRun],
    rubric: Rubric,
    llm_svc: LLMService,
    callback: JudgeResultCompletionCallback | None = None,
    rollouts_per_input: int = 1,
    max_concurrent_llm_calls: int = 100,
    variant: Literal["majority", "multi-reflect"] = "majority",
):
    """TODO(mengk): once we have more global LLM API limiting and scheduling, remove the hacky
    max_concurrent_llm_calls parameter.
    """

    if max_concurrent_llm_calls <= 0:
        raise ValueError("max_concurrent_llm_calls must be greater than 0")
    if rollouts_per_input <= 0:
        raise ValueError("rollouts_per_input must be greater than 0")

    max_concurrent_rubrics = max(1, max_concurrent_llm_calls // rollouts_per_input)
    semaphore = anyio.Semaphore(max_concurrent_rubrics)

    agent_results: list[JudgeResult | None] = [None for _ in agent_runs]
    progress_bar = tqdm(
        total=len(agent_runs),
        desc="Running rubric on agent runs",
        disable=not agent_runs,
    )

    async def _run_single_judge(index: int, agent_run: AgentRun):
        async with semaphore:
            if variant == "majority":
                judge_obj = MajorityVotingJudge(rubric, rollouts_per_input, llm_svc)
            elif variant == "multi-reflect":
                judge_obj = MultiReflectionJudge(rubric, rollouts_per_input, llm_svc)
            else:
                raise ValueError(f"Invalid variant: {variant}")

            start_perf_counter = time.perf_counter()
            result = await judge_obj(
                agent_run,
                max_concurrency=min(rollouts_per_input, max_concurrent_llm_calls),
            )
            duration_seconds = time.perf_counter() - start_perf_counter

        if result is not None:
            result = result.model_copy(
                update={
                    "result_metadata": (result.result_metadata or {})
                    | {"duration_seconds": duration_seconds}
                }
            )

        agent_results[index] = result

        if callback is not None:
            await callback(index, [result] if result is not None else None)
        progress_bar.update()

    try:
        async with anyio.create_task_group() as tg:
            for index, agent_run in enumerate(agent_runs):
                tg.start_soon(_run_single_judge, index, agent_run)
    finally:
        progress_bar.close()

    return agent_results
