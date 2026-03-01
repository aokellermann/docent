#!/usr/bin/env python3
"""
Generate k rubric variants from user data, evaluate on a holdout split, and report per-key accuracy.

Pipeline:
1. Load base rubric from collection/rubric IDs.
2. Load user data JSON.
3. Split run feedback units into train/test by ratio.
4. Infer user model from train split feedback only.
5. Generate k independent rubric rewrites from the base rubric.
6. Run each rubric as a judge on holdout labeled subsets.
7. Report and persist per-key accuracy metrics.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import anyio
from pydantic import BaseModel
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from tqdm import tqdm

from docent import Docent
from docent._llm_util.llm_svc import BaseLLMService
from docent._llm_util.providers.preference_types import ModelOption
from docent.data_models.agent_run import AgentRun
from docent.judges.runner import run_rubric
from docent.judges.types import JudgeResult, ResultType, Rubric
from docent_core._env_util import ENV
from docent_core.docent.ai_tools.rubric.elicit import (
    build_user_context_inference_prompt_with_agent_runs,
    infer_user_context_from_user_data,
)
from docent_core.docent.ai_tools.rubric.rewrite import rewrite_rubric
from docent_core.docent.ai_tools.rubric.user_model import AgentRunFeedback, LabeledRun, UserData

console = Console()

_USER_DATA_TOP_LEVEL_KEYS = {
    "initial_rubric",
    "agent_run_feedbacks",
    "created_at",
    "last_updated",
}


class PerLabelResult(BaseModel):
    agent_run_id: str
    gold_label_value: dict[str, Any]
    rollout_outputs: list[dict[str, Any] | None]
    scored_keys: list[str]
    per_key_accuracy: dict[str, float]
    missing_prediction_rollouts: int


class SplitEvaluation(BaseModel):
    split: str
    total_examples: int
    scored_examples: int
    num_rollouts_per_run: int
    total_expected_rollouts: int
    total_received_rollouts: int
    missing_predictions: int
    total_scored_keys: int
    total_correct_keys: int
    overall_key_accuracy: float | None
    per_key_accuracy: dict[str, float]
    per_label_results: list[PerLabelResult]


class CandidateEvaluation(BaseModel):
    candidate_index: int
    rubric_id: str
    rubric_version: int
    train_evaluation: SplitEvaluation
    test_evaluation: SplitEvaluation
    rubric_text: str
    output_schema: dict[str, Any]


class HoldoutEvaluationReport(BaseModel):
    created_at: datetime
    collection_id: str
    base_rubric_id: str
    base_rubric_version: int
    base_rubric_text: str
    base_output_schema: dict[str, Any]
    user_data_json_path: str
    k: int
    train_ratio: float
    seed: int
    max_llm_concurrency: int
    n_rollouts_per_run: int
    train_feedback_agent_run_ids: list[str]
    test_feedback_agent_run_ids: list[str]
    train_labeled_agent_run_ids: list[str]
    test_labeled_agent_run_ids: list[str]
    num_total_feedback_units: int
    num_train_feedback_units: int
    num_test_feedback_units: int
    num_total_labeled_units: int
    num_train_labeled_units: int
    num_test_labeled_units: int
    num_train_labeled_units_used: int
    num_train_labeled_units_skipped_missing_run: int
    num_test_labeled_units_used: int
    num_test_labeled_units_skipped_missing_run: int
    user_data_summary: str
    user_model_text: str
    rewrite_instructions: str
    candidate_evaluations: list[CandidateEvaluation]


def _coerce_string_keyed_dict(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    parsed: dict[str, Any] = {}
    for key, item in cast(dict[object, object], value).items():
        if not isinstance(key, str):
            return None
        parsed[key] = item
    return parsed


def _require_docent_client() -> Docent:
    _ = ENV
    return Docent()


def _require_openai_api_key() -> None:
    if not ENV.get("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY must be set in environment variables")


def _load_user_data(initial_rubric: str, user_data_json_path: str) -> UserData:
    path = Path(user_data_json_path)
    if not path.exists():
        raise ValueError(f"--user-data-json file does not exist: {path}")

    payload_raw = json.loads(path.read_text(encoding="utf-8"))
    payload_dict = _coerce_string_keyed_dict(payload_raw)
    if payload_dict is None:
        raise ValueError("--user-data-json must contain a JSON object matching UserData")

    extra_keys = sorted(set(payload_dict.keys()) - _USER_DATA_TOP_LEVEL_KEYS)
    if extra_keys:
        raise ValueError(
            "--user-data-json has unexpected top-level key(s): "
            + ", ".join(extra_keys)
            + ". Expected a UserData JSON object."
        )

    user_data = UserData.model_validate(payload_dict)
    if user_data.initial_rubric != initial_rubric:
        console.print(
            "[yellow]Loaded user_data.initial_rubric differs from current rubric; "
            "overriding with current rubric text.[/yellow]"
        )
    user_data.initial_rubric = initial_rubric
    return user_data


def _split_feedback_units(
    feedback_units: Sequence[AgentRunFeedback],
    train_ratio: float,
    seed: int,
) -> tuple[list[AgentRunFeedback], list[AgentRunFeedback]]:
    if not (0.0 < train_ratio):
        raise ValueError("train_ratio must satisfy 0 < train_ratio")
    if not feedback_units:
        raise ValueError("UserData must contain at least 1 feedback unit for holdout evaluation")

    shuffled = list(feedback_units)
    random.Random(seed).shuffle(shuffled)

    train_size = int(len(shuffled) * train_ratio)
    train_size = max(1, min(train_size, len(shuffled)))
    train_units = shuffled[:train_size]
    test_units = shuffled[train_size:]
    return train_units, test_units


def _extract_labeled_runs(feedback_units: Sequence[AgentRunFeedback]) -> list[LabeledRun]:
    labeled_runs: list[LabeledRun] = []
    for feedback in feedback_units:
        if feedback.label is None:
            continue
        if feedback.label.agent_run_id == feedback.agent_run_id:
            labeled_runs.append(feedback.label)
            continue
        labeled_runs.append(
            feedback.label.model_copy(update={"agent_run_id": feedback.agent_run_id})
        )
    return labeled_runs


def _build_train_user_data(
    user_data: UserData,
    train_feedback_units: list[AgentRunFeedback],
    initial_rubric: str,
) -> UserData:
    train_user_data = user_data.model_copy(deep=True)
    train_user_data.initial_rubric = initial_rubric
    train_user_data.agent_run_feedbacks = train_feedback_units
    return train_user_data


def _get_user_data_agent_run_ids(user_data: UserData) -> list[str]:
    return sorted({feedback.agent_run_id for feedback in user_data.agent_run_feedbacks})


def _load_agent_runs_by_ids(
    dc: Docent,
    collection_id: str,
    run_ids: Sequence[str],
    progress_desc: str,
) -> dict[str, AgentRun]:
    agent_runs_by_id: dict[str, AgentRun] = {}
    for run_id in tqdm(run_ids, desc=progress_desc):
        run = dc.get_agent_run(collection_id, run_id)
        if run is None:
            console.print(f"[yellow]Warning:[/yellow] missing agent run {run_id}")
            continue
        agent_runs_by_id[run_id] = run
    return agent_runs_by_id


def _default_output_json_path() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return str(Path("outputs") / f"holdout_k_rubrics_eval_{timestamp}_gitignore.json")


def _build_rewrite_instructions(user_data_summary: str, user_model_text: str) -> str:
    return f"""Use the following user model and user-data summary to rewrite the rubric so the rubric better captures how this specific user labels runs.

IMPORTANT:
- Keep the rubric concise and operational.
- Keep schema changes minimal unless needed.
- Ensure rubric decision logic matches the user's demonstrated labeling behavior.

USER MODEL (z):
{user_model_text}

USER DATA SUMMARY STRING (exact summary used to infer z):
{user_data_summary}
"""


def _find_rank_accuracy_value(candidate: CandidateEvaluation) -> float:
    if candidate.test_evaluation.overall_key_accuracy is None:
        return -1.0
    return candidate.test_evaluation.overall_key_accuracy


def _render_split_summary(
    total_feedback_units: int,
    train_feedback_units: list[AgentRunFeedback],
    test_feedback_units: list[AgentRunFeedback],
    train_labeled_runs: list[LabeledRun],
    test_labeled_runs: list[LabeledRun],
) -> None:
    console.print(
        "Loaded "
        f"{total_feedback_units} feedback unit(s); split into "
        f"{len(train_feedback_units)} train / {len(test_feedback_units)} test units. "
        f"Labeled subsets: {len(train_labeled_runs)} train / {len(test_labeled_runs)} test."
    )


def _render_candidate_summary(candidates: Sequence[CandidateEvaluation]) -> None:
    n_rollouts = candidates[0].test_evaluation.num_rollouts_per_run if candidates else "N/A"
    table = Table(title=f"Candidate Accuracy (Per-Key, n={n_rollouts})")
    table.add_column("Rank", justify="right")
    table.add_column("Candidate", justify="right")
    table.add_column("n", justify="right")
    table.add_column("Test Overall", justify="right")
    table.add_column("Test C/T", justify="right")
    table.add_column("Train Overall", justify="right")
    table.add_column("Train C/T", justify="right")

    ranked = sorted(candidates, key=_find_rank_accuracy_value, reverse=True)
    for rank, candidate in enumerate(ranked, 1):
        test_overall = (
            f"{candidate.test_evaluation.overall_key_accuracy:.4f}"
            if candidate.test_evaluation.overall_key_accuracy is not None
            else "N/A"
        )
        train_overall = (
            f"{candidate.train_evaluation.overall_key_accuracy:.4f}"
            if candidate.train_evaluation.overall_key_accuracy is not None
            else "N/A"
        )
        table.add_row(
            str(rank),
            str(candidate.candidate_index),
            str(candidate.test_evaluation.num_rollouts_per_run),
            test_overall,
            f"{candidate.test_evaluation.total_correct_keys}/{candidate.test_evaluation.total_scored_keys}",
            train_overall,
            f"{candidate.train_evaluation.total_correct_keys}/{candidate.train_evaluation.total_scored_keys}",
        )
    console.print(table)


def _render_top_candidate_details(candidates: Sequence[CandidateEvaluation]) -> None:
    ranked = sorted(candidates, key=_find_rank_accuracy_value, reverse=True)
    if not ranked:
        return
    top = ranked[0]
    test_per_key_lines = "\n".join(
        f"- {key}: {value:.4f}"
        for key, value in sorted(top.test_evaluation.per_key_accuracy.items())
    )
    train_per_key_lines = "\n".join(
        f"- {key}: {value:.4f}"
        for key, value in sorted(top.train_evaluation.per_key_accuracy.items())
    )
    if not test_per_key_lines:
        test_per_key_lines = "- (No scored keys)"
    if not train_per_key_lines:
        train_per_key_lines = "- (No scored keys)"
    console.print(
        Panel(
            f"[bold]Top candidate:[/bold] {top.candidate_index}\n"
            f"[bold]Rollouts per run (n):[/bold] {top.test_evaluation.num_rollouts_per_run}\n"
            f"[bold]Test overall per-key accuracy:[/bold] "
            f"{top.test_evaluation.overall_key_accuracy if top.test_evaluation.overall_key_accuracy is not None else 'N/A'}\n"
            f"[bold]Train overall per-key accuracy:[/bold] "
            f"{top.train_evaluation.overall_key_accuracy if top.train_evaluation.overall_key_accuracy is not None else 'N/A'}\n\n"
            f"[bold]Test per-key accuracy:[/bold]\n{test_per_key_lines}\n\n"
            f"[bold]Train per-key accuracy:[/bold]\n{train_per_key_lines}",
            title="[bold]Best Candidate[/bold]",
            expand=False,
        )
    )


async def _generate_rubric_candidates(
    base_rubric: Rubric,
    k: int,
    rewrite_instructions: str,
    llm_svc: BaseLLMService,
) -> list[Rubric]:
    candidates: list[Rubric | None] = [None] * k

    async def _generate_one(idx: int) -> None:
        console.print(f"Generating rubric candidate {idx + 1}/{k}")
        rewritten = await rewrite_rubric(
            rubric=base_rubric,
            instructions=rewrite_instructions,
            model_options=[
                ModelOption(
                    provider="openrouter",
                    model_name="openai/gpt-5.2",
                    reasoning_effort=None,
                )
            ],
            llm_svc=llm_svc,
        )
        unique_id = str(uuid4())
        rewritten_with_unique_id = rewritten.model_copy(update={"id": unique_id})
        candidates[idx] = rewritten_with_unique_id
        console.print(
            Panel(
                rewritten_with_unique_id.rubric_text,
                title=f"[bold]Rubric Candidate {idx + 1}/{k}[/bold]",
                expand=False,
            )
        )

    async with anyio.create_task_group() as tg:
        for idx in range(k):
            tg.start_soon(_generate_one, idx)

    return [candidate for candidate in candidates if candidate is not None]


def _evaluate_split_per_key_accuracy(
    split_name: str,
    judge_results: Sequence[JudgeResult],
    labels: Sequence[LabeledRun],
    n_rollouts_per_run: int,
) -> SplitEvaluation:
    if n_rollouts_per_run <= 0:
        raise ValueError("n_rollouts_per_run must be > 0")

    result_by_run_id: dict[str, list[JudgeResult]] = defaultdict(list)
    for result in judge_results:
        result_by_run_id[result.agent_run_id].append(result)

    per_key_correct_counts: dict[str, int] = defaultdict(int)
    per_key_total_counts: dict[str, int] = defaultdict(int)

    missing_predictions = 0
    total_expected_rollouts = len(labels) * n_rollouts_per_run
    total_received_rollouts = 0
    total_scored_keys = 0
    total_correct_keys = 0
    scored_examples = 0

    per_label_results: list[PerLabelResult] = []
    for label in labels:
        scored_keys = list(label.label_value.keys())
        if not scored_keys:
            per_label_results.append(
                PerLabelResult(
                    agent_run_id=label.agent_run_id,
                    gold_label_value=label.label_value,
                    rollout_outputs=[],
                    scored_keys=[],
                    per_key_accuracy={},
                    missing_prediction_rollouts=0,
                )
            )
            continue

        scored_examples += 1

        run_results = result_by_run_id.get(label.agent_run_id, [])
        total_received_rollouts += len(run_results)
        rollout_outputs: list[dict[str, Any] | None] = []
        per_key_label_correct_counts: dict[str, int] = defaultdict(int)
        per_label_missing_rollouts = 0

        for rollout_idx in range(n_rollouts_per_run):
            judge_result = run_results[rollout_idx] if rollout_idx < len(run_results) else None
            if judge_result is None or judge_result.result_type != ResultType.DIRECT_RESULT:
                missing_predictions += 1
                per_label_missing_rollouts += 1
                judge_output: dict[str, Any] | None = None
            else:
                judge_output = judge_result.output

            rollout_outputs.append(judge_output)

            for key in scored_keys:
                per_key_total_counts[key] += 1
                total_scored_keys += 1

                if judge_output is None or key not in judge_output:
                    continue
                if judge_output[key] == label.label_value[key]:
                    per_key_label_correct_counts[key] += 1
                    per_key_correct_counts[key] += 1
                    total_correct_keys += 1

        per_label_per_key_accuracy = {
            key: (per_key_label_correct_counts[key] / n_rollouts_per_run) for key in scored_keys
        }

        per_label_results.append(
            PerLabelResult(
                agent_run_id=label.agent_run_id,
                gold_label_value=label.label_value,
                rollout_outputs=rollout_outputs,
                scored_keys=scored_keys,
                per_key_accuracy=per_label_per_key_accuracy,
                missing_prediction_rollouts=per_label_missing_rollouts,
            )
        )

    overall_key_accuracy = (
        (total_correct_keys / total_scored_keys) if total_scored_keys > 0 else None
    )
    per_key_accuracy = {
        key: (per_key_correct_counts[key] / total)
        for key, total in per_key_total_counts.items()
        if total > 0
    }

    return SplitEvaluation(
        split=split_name,
        total_examples=len(labels),
        scored_examples=scored_examples,
        num_rollouts_per_run=n_rollouts_per_run,
        total_expected_rollouts=total_expected_rollouts,
        total_received_rollouts=total_received_rollouts,
        missing_predictions=missing_predictions,
        total_scored_keys=total_scored_keys,
        total_correct_keys=total_correct_keys,
        overall_key_accuracy=overall_key_accuracy,
        per_key_accuracy=per_key_accuracy,
        per_label_results=per_label_results,
    )


async def _evaluate_candidates(
    candidates: Sequence[Rubric],
    train_agent_runs: Sequence[AgentRun],
    train_labels: Sequence[LabeledRun],
    test_agent_runs: Sequence[AgentRun],
    test_labels: Sequence[LabeledRun],
    llm_svc: BaseLLMService,
    judge_timeout: float,
    n_rollouts_per_run: int,
) -> list[CandidateEvaluation]:
    evaluations: list[CandidateEvaluation | None] = [None] * len(candidates)

    async def _evaluate_one(idx_zero_based: int, candidate: Rubric) -> None:
        # TODO(mengk), FIXME(mengk): remove this!!
        candidate = candidate.model_copy(
            update={
                "judge_model": ModelOption(
                    provider="openrouter",
                    model_name="google/gemini-3-flash-preview",
                    reasoning_effort=None,
                )
            }
        )

        idx = idx_zero_based + 1
        console.print(f"Running candidate {idx}/{len(candidates)}")
        console.print(
            f"- train split: {len(train_agent_runs)} runs x {n_rollouts_per_run} rollouts"
        )
        if train_agent_runs:
            train_judge_results = await run_rubric(
                agent_runs=train_agent_runs,
                rubric=candidate,
                llm_svc=llm_svc,
                n_rollouts_per_input=n_rollouts_per_run,
                show_progress=True,
                timeout=judge_timeout,
            )
        else:
            train_judge_results = []

        console.print(f"- test split: {len(test_agent_runs)} runs x {n_rollouts_per_run} rollouts")
        if test_agent_runs:
            test_judge_results = await run_rubric(
                agent_runs=test_agent_runs,
                rubric=candidate,
                llm_svc=llm_svc,
                n_rollouts_per_input=n_rollouts_per_run,
                show_progress=True,
                timeout=judge_timeout,
            )
        else:
            test_judge_results = []

        train_evaluation = _evaluate_split_per_key_accuracy(
            split_name="train",
            judge_results=train_judge_results,
            labels=train_labels,
            n_rollouts_per_run=n_rollouts_per_run,
        )
        test_evaluation = _evaluate_split_per_key_accuracy(
            split_name="test",
            judge_results=test_judge_results,
            labels=test_labels,
            n_rollouts_per_run=n_rollouts_per_run,
        )

        evaluations[idx_zero_based] = CandidateEvaluation(
            candidate_index=idx,
            rubric_id=candidate.id,
            rubric_version=candidate.version,
            train_evaluation=train_evaluation,
            test_evaluation=test_evaluation,
            rubric_text=candidate.rubric_text,
            output_schema=candidate.output_schema,
        )

    async with anyio.create_task_group() as tg:
        for idx_zero_based, candidate in enumerate(candidates):
            tg.start_soon(_evaluate_one, idx_zero_based, candidate)

    if any(evaluation is None for evaluation in evaluations):
        raise RuntimeError("Candidate evaluation did not complete for all candidates")
    return cast(list[CandidateEvaluation], evaluations)


def _write_report_json(report: HoldoutEvaluationReport, output_json_path: str | None) -> Path:
    path = (
        Path(output_json_path)
        if output_json_path is not None
        else Path(_default_output_json_path())
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


async def run_holdout_k_rubrics_evaluation(
    collection_id: str,
    rubric_id: str,
    user_data_json_path: str,
    k: int,
    train_ratio: float,
    seed: int,
    output_json_path: str | None,
    max_llm_concurrency: int,
    judge_timeout: float,
    n_rollouts_per_run: int,
) -> None:
    if k <= 0:
        raise ValueError("k must be > 0")
    if max_llm_concurrency <= 0:
        raise ValueError("max_llm_concurrency must be > 0")
    if judge_timeout <= 0:
        raise ValueError("judge_timeout must be > 0")
    if n_rollouts_per_run <= 0:
        raise ValueError("n_rollouts_per_run must be > 0")

    console.print("[bold]Initializing clients...[/bold]")
    dc = _require_docent_client()
    _require_openai_api_key()
    llm_svc = BaseLLMService(max_concurrency=max_llm_concurrency)

    base_rubric = dc.get_rubric(collection_id, rubric_id)
    console.print(f"Loaded base rubric {base_rubric.id} v{base_rubric.version}")

    user_data = _load_user_data(
        initial_rubric=base_rubric.rubric_text,
        user_data_json_path=user_data_json_path,
    )
    train_feedback_units, test_feedback_units = _split_feedback_units(
        user_data.agent_run_feedbacks, train_ratio=train_ratio, seed=seed
    )
    train_labels = _extract_labeled_runs(train_feedback_units)
    test_labels_all = _extract_labeled_runs(test_feedback_units)
    _render_split_summary(
        total_feedback_units=len(user_data.agent_run_feedbacks),
        train_feedback_units=train_feedback_units,
        test_feedback_units=test_feedback_units,
        train_labeled_runs=train_labels,
        test_labeled_runs=test_labels_all,
    )
    if not train_labels:
        console.print(
            "[yellow]Warning:[/yellow] no labeled train units available; train accuracy will be N/A."
        )
    if not test_labels_all:
        console.print(
            "[yellow]Warning:[/yellow] no labeled test units available; test accuracy will be N/A."
        )

    train_user_data = _build_train_user_data(
        user_data=user_data,
        train_feedback_units=train_feedback_units,
        initial_rubric=base_rubric.rubric_text,
    )
    train_run_ids = _get_user_data_agent_run_ids(train_user_data)
    train_agent_runs_by_id = _load_agent_runs_by_ids(
        dc=dc,
        collection_id=collection_id,
        run_ids=train_run_ids,
        progress_desc="Fetching train-context runs",
    )

    user_data_summary, _ = await build_user_context_inference_prompt_with_agent_runs(
        user_data=train_user_data,
        agent_runs_by_id=train_agent_runs_by_id,
        llm_svc=llm_svc,
    )
    user_model_text = await infer_user_context_from_user_data(
        user_data=train_user_data,
        llm_svc=llm_svc,
        user_data_summary=user_data_summary,
    )

    rewrite_instructions = _build_rewrite_instructions(
        user_data_summary=user_data_summary,
        user_model_text=user_model_text,
    )
    rubric_candidates = await _generate_rubric_candidates(
        base_rubric=base_rubric,
        k=k,
        rewrite_instructions=rewrite_instructions,
        llm_svc=llm_svc,
    )

    train_labels_for_eval = [
        label for label in train_labels if label.agent_run_id in train_agent_runs_by_id
    ]
    skipped_missing_train_runs = len(train_labels) - len(train_labels_for_eval)
    if skipped_missing_train_runs > 0:
        console.print(
            "[yellow]Warning:[/yellow] "
            f"skipping {skipped_missing_train_runs} train labeled unit(s) with missing runs"
        )
    if not train_labels_for_eval:
        console.print(
            "[yellow]Warning:[/yellow] no train labeled units available; train scoring will be N/A"
        )
    ordered_train_run_ids = sorted({label.agent_run_id for label in train_labels_for_eval})
    train_agent_runs = [train_agent_runs_by_id[run_id] for run_id in ordered_train_run_ids]

    test_run_ids = sorted({label.agent_run_id for label in test_labels_all})
    test_agent_runs_by_id = _load_agent_runs_by_ids(
        dc=dc,
        collection_id=collection_id,
        run_ids=test_run_ids,
        progress_desc="Fetching test runs",
    )

    test_labels = [
        label for label in test_labels_all if label.agent_run_id in test_agent_runs_by_id
    ]
    skipped_missing_test_runs = len(test_labels_all) - len(test_labels)
    if skipped_missing_test_runs > 0:
        console.print(
            "[yellow]Warning:[/yellow] "
            f"skipping {skipped_missing_test_runs} test labeled unit(s) with missing runs"
        )
    if not test_labels:
        console.print(
            "[yellow]Warning:[/yellow] no test labeled units available; test scoring will be N/A"
        )

    ordered_test_run_ids = sorted({label.agent_run_id for label in test_labels})
    test_agent_runs = [test_agent_runs_by_id[run_id] for run_id in ordered_test_run_ids]

    candidate_evaluations = await _evaluate_candidates(
        candidates=rubric_candidates,
        train_agent_runs=train_agent_runs,
        train_labels=train_labels_for_eval,
        test_agent_runs=test_agent_runs,
        test_labels=test_labels,
        llm_svc=llm_svc,
        judge_timeout=judge_timeout,
        n_rollouts_per_run=n_rollouts_per_run,
    )
    _render_candidate_summary(candidate_evaluations)
    _render_top_candidate_details(candidate_evaluations)

    report = HoldoutEvaluationReport(
        created_at=datetime.now(timezone.utc),
        collection_id=collection_id,
        base_rubric_id=base_rubric.id,
        base_rubric_version=base_rubric.version,
        base_rubric_text=base_rubric.rubric_text,
        base_output_schema=base_rubric.output_schema,
        user_data_json_path=user_data_json_path,
        k=k,
        train_ratio=train_ratio,
        seed=seed,
        max_llm_concurrency=max_llm_concurrency,
        n_rollouts_per_run=n_rollouts_per_run,
        train_feedback_agent_run_ids=[unit.agent_run_id for unit in train_feedback_units],
        test_feedback_agent_run_ids=[unit.agent_run_id for unit in test_feedback_units],
        train_labeled_agent_run_ids=[label.agent_run_id for label in train_labels],
        test_labeled_agent_run_ids=[label.agent_run_id for label in test_labels_all],
        num_total_feedback_units=len(user_data.agent_run_feedbacks),
        num_train_feedback_units=len(train_feedback_units),
        num_test_feedback_units=len(test_feedback_units),
        num_total_labeled_units=len(train_labels) + len(test_labels_all),
        num_train_labeled_units=len(train_labels),
        num_test_labeled_units=len(test_labels_all),
        num_train_labeled_units_used=len(train_labels_for_eval),
        num_train_labeled_units_skipped_missing_run=skipped_missing_train_runs,
        num_test_labeled_units_used=len(test_labels),
        num_test_labeled_units_skipped_missing_run=skipped_missing_test_runs,
        user_data_summary=user_data_summary,
        user_model_text=user_model_text,
        rewrite_instructions=rewrite_instructions,
        candidate_evaluations=candidate_evaluations,
    )
    output_path = _write_report_json(report, output_json_path)
    console.print(f"\nWrote evaluation report to [bold]{output_path}[/bold]")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate k rewritten rubrics from train user data and report holdout per-key accuracy."
        )
    )
    parser.add_argument("collection_id", type=str, help="Collection ID")
    parser.add_argument("rubric_id", type=str, help="Base rubric ID")
    parser.add_argument(
        "--user-data-json",
        type=str,
        required=True,
        help="Path to UserData JSON used for train/test holdout split",
    )
    parser.add_argument("--k", type=int, required=True, help="Number of rubric candidates")
    parser.add_argument(
        "--train-ratio",
        type=float,
        required=True,
        help="Train ratio over feedback units (0 < train_ratio)",
    )
    parser.add_argument("--seed", type=int, default=0, help="Random seed (default: 0)")
    parser.add_argument(
        "--max-llm-concurrency",
        type=int,
        default=100,
        help="LLM max concurrency (default: 100)",
    )
    parser.add_argument(
        "--judge-timeout",
        type=float,
        default=180.0,
        help="Per-judge timeout in seconds (default: 180.0)",
    )
    parser.add_argument(
        "--n-rollouts-per-run",
        type=int,
        default=3,
        help="Number of judge rollouts per agent run when estimating train/test accuracy (default: 1)",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default=None,
        help="Optional output JSON path (default: outputs/holdout_k_rubrics_eval_<ts>_gitignore.json)",
    )
    args = parser.parse_args()

    try:
        asyncio.run(
            run_holdout_k_rubrics_evaluation(
                collection_id=args.collection_id,
                rubric_id=args.rubric_id,
                user_data_json_path=args.user_data_json,
                k=args.k,
                train_ratio=args.train_ratio,
                seed=args.seed,
                output_json_path=args.output_json,
                max_llm_concurrency=args.max_llm_concurrency,
                judge_timeout=args.judge_timeout,
                n_rollouts_per_run=args.n_rollouts_per_run,
            )
        )
    except KeyboardInterrupt:
        console.print("\nInterrupted by user")
        sys.exit(1)
    except Exception as exc:
        console.print(f"\n[red]ERROR:[/red] {exc}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
