"""Utility helpers for running rubric evaluations against stored agent runs."""

import json
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import anyio
from pydantic import BaseModel, Field
from tqdm.auto import tqdm

from docent._log_util import get_logger
from docent.data_models.agent_run import AgentRun
from docent_core._db_service.db import DocentDB
from docent_core._llm_util.providers.preferences import ModelOption
from docent_core.docent.ai_tools.rubric.rubric import JudgeResult, Rubric, evaluate_rubric
from docent_core.docent.services.llms import LLMService, UsageService
from docent_core.docent.services.monoservice import MonoService

logger = get_logger(__name__)

DEFAULT_USER_EMAIL = "mengk@mit.edu"


class RubricEvaluationParams(BaseModel):
    rollouts_per_input: int
    judge_variant: Literal["majority", "multi-reflect"]
    judge_model: ModelOption
    id: str = Field(default_factory=lambda: str(uuid4()))


class ExperimentResultDump(BaseModel):
    params: RubricEvaluationParams
    results: list[JudgeResult | None]


class RunMeasurement(BaseModel):
    agent_run_id: str
    label_missing: bool = False
    agreement_fraction: float | None = None
    per_key_correct: dict[str, bool] | None = None
    per_key_judge_values: dict[str, Any] | None = None
    per_key_gold_values: dict[str, Any] | None = None
    duration_seconds: float | None = None


class AggregateMeasurements(BaseModel):
    measurements: list[RunMeasurement] = Field(default_factory=list)
    num_results: int = 0
    num_missing_results: int = 0
    num_missing_labels: int = 0
    num_scored_results: int = 0
    accuracy: float | None = None
    mean_agreement_fraction: float | None = None
    per_key_accuracy: dict[str, float] = Field(default_factory=dict)
    mean_duration_seconds: float | None = None


async def run_rubric_evaluation(
    agent_runs: list[AgentRun],
    rubric_text: str,
    rubric_output_schema: dict[str, Any],
    params: RubricEvaluationParams,
) -> list[JudgeResult | None]:
    """Execute a rubric judging run with the provided parameters and return the results."""
    db = await DocentDB.init()

    async with db.session():
        mono_svc = MonoService(db)
        usage_svc = UsageService(db.session)
        user = await mono_svc.get_user_by_email(DEFAULT_USER_EMAIL)
        if user is None:
            raise ValueError(f"User {DEFAULT_USER_EMAIL} not found")

        llm_svc = LLMService(db.session, user, usage_svc)

        rubric = Rubric(
            rubric_text=rubric_text,
            output_schema=rubric_output_schema,
            judge_model=params.judge_model,
        )

        judge_results = await evaluate_rubric(
            agent_runs,
            rubric,
            llm_svc,
            rollouts_per_input=params.rollouts_per_input,
            variant=params.judge_variant,
        )

    return judge_results


async def run_experiments(
    agent_runs: list[AgentRun],
    rubric_text: str,
    rubric_output_schema: dict[str, Any],
    all_params: list[RubricEvaluationParams],
    result_fpath: Path,
    max_parallel_experiments: int = 4,
) -> dict[str, ExperimentResultDump]:
    if result_fpath.exists():
        raise FileExistsError(f"Result file already exists: {result_fpath}")
    experiment_results: dict[str, ExperimentResultDump] = {}
    results_lock = anyio.Lock()
    progress_lock = anyio.Lock()
    total_experiments = len(all_params)

    logger.info(
        "Starting rubric experiments (%d variants); results will be written to %s",
        total_experiments,
        result_fpath,
    )
    progress = tqdm(
        total=total_experiments,
        desc="Rubric experiments",
        unit="exp",
        leave=False,
    )

    async def _record_results(
        params: RubricEvaluationParams, judge_results: list[JudgeResult | None]
    ):
        params_id = params.id

        async with results_lock:
            experiment_results[params_id] = ExperimentResultDump(
                params=params, results=judge_results
            )

            # Persist experiment_results
            result_fpath.parent.mkdir(parents=True, exist_ok=True)
            # Using tmp_path makes things atomic
            tmp_path = result_fpath.with_suffix(".tmp")
            serialized_payload = {
                exp_id: exp_dump.model_dump(mode="json")
                for exp_id, exp_dump in experiment_results.items()
            }
            tmp_path.write_text(json.dumps(serialized_payload, indent=2, sort_keys=True))
            tmp_path.replace(result_fpath)

        async with progress_lock:
            progress.update()

        logger.info(
            "Recorded results for experiment %s (%d judge outputs)",
            params_id,
            len(judge_results),
        )

    semaphore = anyio.Semaphore(max_parallel_experiments)

    async def _run_single(params: RubricEvaluationParams) -> None:
        logger.info(
            "Starting experiment %s: model=%s variant=%s rollouts=%s",
            params.id,
            params.judge_model,
            params.judge_variant,
            params.rollouts_per_input,
        )

        async with semaphore:
            judge_results = await run_rubric_evaluation(
                agent_runs,
                rubric_text,
                rubric_output_schema,
                params,
            )

        await _record_results(params, judge_results)

        logger.info("Finished experiment %s", params.id)

    try:
        async with anyio.create_task_group() as tg:
            for params in all_params:
                tg.start_soon(_run_single, params)
    finally:
        progress.close()
        logger.info(
            "Completed rubric experiments: %d/%d finished",
            len(experiment_results),
            total_experiments,
        )

    return experiment_results


def load_experiment_results(result_fpath: Path) -> dict[str, ExperimentResultDump]:
    """Load rubric experiment results previously saved by run_experiments."""
    if not result_fpath.exists():
        raise FileNotFoundError(f"Result file not found: {result_fpath}")

    raw_results = json.loads(result_fpath.read_text())

    experiment_results: dict[str, ExperimentResultDump] = {}
    for params_id, serialized_dump in raw_results.items():
        experiment_results[params_id] = ExperimentResultDump.model_validate(serialized_dump)

    return experiment_results


def compute_measurements(
    judge_results: list[JudgeResult | None],
    ar_to_label: dict[str, dict[str, Any]],
    verbose: bool = False,
):
    """
    What do I even want to measure?
    For each judge result:
        Understanding the final result:
            Whether it matches the gold label completely or partially: fraction of agt keys that are correct
            How frequently it will be correct if I roll the judge out multiple times.
                I think this is only valid to measure through the mode ratio of the majority variant.
                The multi-reflect variant doesn't have independent draws, so omit that for now.
    At an aggregate level
        Average agreement, marginalized over all results and keys
        Average agreement, marginalized over all results (but broken down by key)
        Average duration of each result being computed

    Notice agt_keys in ai_tools/rubric.py. You can safely assume that these keys are in ar_to_label, and you can directly access them.
        If the key does not exist, it is find for the code to error.
    """
    measurements: list[RunMeasurement] = []
    num_missing_results = 0
    num_missing_labels = 0
    num_scored_results = 0

    total_correct_keys = 0
    total_keys = 0
    per_key_counts: dict[str, dict[str, int]] = {}

    agreement_fractions: list[float] = []
    durations: list[float] = []

    for result in judge_results:
        if result is None:
            num_missing_results += 1
            continue

        metadata = result.result_metadata or {}
        run_measurement = RunMeasurement(agent_run_id=result.agent_run_id)

        duration_seconds = metadata["duration_seconds"]
        run_measurement.duration_seconds = float(duration_seconds)
        durations.append(float(duration_seconds))

        gold_label = ar_to_label.get(result.agent_run_id)
        if gold_label is None:
            num_missing_labels += 1
            run_measurement.label_missing = True
            measurements.append(run_measurement)
            if verbose:
                logger.warning("Missing gold label for agent_run_id=%s", result.agent_run_id)
            continue

        agt_keys = list[str](metadata["agt_keys"])

        per_key_correct: dict[str, bool] = {}
        per_key_judge_values: dict[str, Any] = {}
        per_key_gold_values: dict[str, Any] = {}

        for key in agt_keys:
            judge_value = result.output[key]
            gold_value = gold_label[key]
            is_correct = judge_value == gold_value

            per_key_correct[key] = is_correct
            per_key_judge_values[key] = judge_value
            per_key_gold_values[key] = gold_value

            total_correct_keys += int(is_correct)
            total_keys += 1

            key_counts = per_key_counts.setdefault(key, {"correct": 0, "total": 0})
            key_counts["total"] += 1
            if is_correct:
                key_counts["correct"] += 1

        if per_key_correct:
            agreement_fraction = sum(int(val) for val in per_key_correct.values()) / len(
                per_key_correct
            )
            run_measurement.agreement_fraction = agreement_fraction
            agreement_fractions.append(agreement_fraction)

        run_measurement.per_key_correct = per_key_correct or None
        run_measurement.per_key_judge_values = per_key_judge_values or None
        run_measurement.per_key_gold_values = per_key_gold_values or None

        num_scored_results += 1
        measurements.append(run_measurement)

        if verbose:
            logger.info(
                "Measurement for agent_run_id=%s -> %s", result.agent_run_id, run_measurement
            )

    accuracy = (total_correct_keys / total_keys) if total_keys else None
    mean_agreement_fraction = (
        sum(agreement_fractions) / len(agreement_fractions) if agreement_fractions else None
    )
    per_key_accuracy = {
        key: counts["correct"] / counts["total"] if counts["total"] else 0.0
        for key, counts in per_key_counts.items()
    }
    mean_duration_seconds = sum(durations) / len(durations) if durations else None

    aggregate = AggregateMeasurements(
        measurements=measurements,
        num_results=len(judge_results),
        num_missing_results=num_missing_results,
        num_missing_labels=num_missing_labels,
        num_scored_results=num_scored_results,
        accuracy=accuracy,
        mean_agreement_fraction=mean_agreement_fraction,
        per_key_accuracy=per_key_accuracy,
        mean_duration_seconds=mean_duration_seconds,
    )

    return aggregate
