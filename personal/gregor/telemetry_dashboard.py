#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import base64
import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Any, Callable, Mapping, Sequence

from sqlalchemy import Integer, and_, case
from sqlalchemy import cast as sa_cast
from sqlalchemy import func, or_, select

from docent_core._worker.constants import WorkerFunction
from docent_core.docent.db.schemas.tables import (
    JobStatus,
    SQLAJob,
    SQLATelemetryAccumulation,
    SQLATelemetryAgentRunStatus,
    TelemetryAgentRunStatus,
)
from docent_core.docent.services.monoservice import MonoService

try:
    from rich.text import Text
    from textual import events
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical
    from textual.reactive import reactive
    from textual.screen import ModalScreen
    from textual.widgets import DataTable, Footer, Input, Static
except ImportError as exc:  # pragma: no cover - Textual is optional
    raise SystemExit(
        "Telemetry dashboard requires the 'textual' package. Install it with 'pip install textual'."
    ) from exc


@dataclass(slots=True)
class JobInfo:
    id: str
    type: str
    status: str
    created_at: datetime
    collection_id: str | None
    telemetry_log_id: str | None
    user_email: str | None
    payload: Mapping[str, Any]


@dataclass(slots=True)
class JobQueueStats:
    job_type: str
    pending: int
    running: int
    completed: int
    recent_completed: int
    completion_rate_per_min: float
    recent_added: int
    recent_added_per_min: float

    @property
    def queued(self) -> int:
        return self.pending + self.running


@dataclass(slots=True)
class CollectionStatusRow:
    collection_id: str
    awaiting: int
    processing: int
    completed: int
    errored: int
    total: int
    recent_completed: int
    completion_rate_per_min: float
    last_updated_at: datetime | None
    last_completed_at: datetime | None

    @property
    def needs_work(self) -> bool:
        return self.awaiting > 0


@dataclass(slots=True)
class AgentRunStatusRow:
    agent_run_id: str
    status: str
    current_version: int
    processed_version: int
    updated_at: datetime | None
    requires_processing: bool
    error_message: str | None


# Sentinel datetime used when ordering missing timestamps
DATETIME_FLOOR = datetime.min.replace(tzinfo=None)

JobSortKey = Callable[[JobInfo], Any]
CollectionSortKey = Callable[[CollectionStatusRow], Any]
AgentRunSortKey = Callable[[AgentRunStatusRow], Any]
IngestSortKey = Callable[[JobInfo], Any]

JOB_SORT_MAP: dict[int, JobSortKey] = {
    0: lambda job: job.status,
    1: lambda job: job.type,
    2: lambda job: job.collection_id or "",
    3: lambda job: job.telemetry_log_id or "",
    4: lambda job: job.user_email or "",
    5: lambda job: job.created_at,
    6: lambda job: job.id,
}

COLLECTION_SORT_MAP: dict[int, CollectionSortKey] = {
    0: lambda row: row.collection_id,
    1: lambda row: row.awaiting,
    2: lambda row: row.processing,
    3: lambda row: row.completed,
    4: lambda row: row.errored,
    5: lambda row: row.total,
    6: lambda row: row.recent_completed,
    7: lambda row: row.completion_rate_per_min,
    8: lambda row: row.last_updated_at or DATETIME_FLOOR,
    9: lambda row: row.last_completed_at or DATETIME_FLOOR,
}

RUN_SORT_MAP: dict[int, AgentRunSortKey] = {
    0: lambda row: row.agent_run_id,
    1: lambda row: row.status,
    2: lambda row: row.current_version - row.processed_version,
    3: lambda row: row.current_version,
    4: lambda row: row.processed_version,
    5: lambda row: row.updated_at or DATETIME_FLOOR,
    6: lambda row: row.error_message or "",
}

INGEST_SORT_MAP: dict[int, IngestSortKey] = {
    0: lambda job: job.status,
    1: lambda job: job.payload.get("telemetry_log_id") or "",
    2: lambda job: job.collection_id or "",
    3: lambda job: job.user_email or "",
    4: lambda job: job.created_at,
    5: lambda job: job.id,
}


def utcnow_naive() -> datetime:
    """Return naive UTC timestamps so comparisons match DB defaults."""
    return datetime.now(UTC).replace(tzinfo=None)


def humanize_timedelta(delta: timedelta) -> str:
    seconds = int(delta.total_seconds())
    if seconds < 0:
        seconds = 0
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h"
    days = hours // 24
    return f"{days}d"


def format_ago(timestamp: datetime | None) -> str:
    if timestamp is None:
        return "—"
    return f"{humanize_timedelta(utcnow_naive() - timestamp)} ago"


def truncate(text: str, max_length: int = 60) -> str:
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 1]}…"


def _telemetry_needs_work_case():
    statuses = SQLATelemetryAgentRunStatus
    errored_version = func.coalesce(
        sa_cast(statuses.metadata_json["errored_version"].astext, Integer),
        0,
    )
    return case(
        (statuses.status == TelemetryAgentRunStatus.NEEDS_PROCESSING.value, 1),
        (
            and_(
                statuses.current_version > statuses.processed_version,
                or_(
                    statuses.status != TelemetryAgentRunStatus.ERROR.value,
                    statuses.current_version > errored_version,
                ),
            ),
            1,
        ),
        else_=0,
    )


def _telemetry_recent_completion_case(cutoff: datetime):
    statuses = SQLATelemetryAgentRunStatus
    return case(
        (
            and_(
                statuses.status == TelemetryAgentRunStatus.COMPLETED.value,
                statuses.updated_at >= cutoff,
            ),
            1,
        ),
        else_=0,
    )


def _status_priority_case():
    statuses = SQLATelemetryAgentRunStatus
    return case(
        (statuses.status == TelemetryAgentRunStatus.NEEDS_PROCESSING.value, 0),
        (statuses.status == TelemetryAgentRunStatus.PROCESSING.value, 1),
        (statuses.status == TelemetryAgentRunStatus.ERROR.value, 2),
        else_=3,
    )


class TelemetryDataProvider:
    """Async helper for fetching telemetry state snapshots."""

    RECENT_COMPLETION_MINUTES = 15
    SLOW_QUERY_SECONDS = 1.0

    def __init__(self) -> None:
        self._mono_svc: MonoService | None = None
        self._logger = logging.getLogger("telemetry_dashboard")

    async def ensure_ready(self) -> None:
        if self._mono_svc is None:
            self._mono_svc = await MonoService.init()

    @property
    def mono_svc(self) -> MonoService:
        if self._mono_svc is None:
            raise RuntimeError("MonoService is not initialized")
        return self._mono_svc

    async def fetch_job_stats(self) -> dict[str, JobQueueStats]:
        started = perf_counter()
        job_types = [
            WorkerFunction.TELEMETRY_INGEST_JOB.value,
            WorkerFunction.TELEMETRY_PROCESSING_JOB.value,
        ]
        recent_cutoff = utcnow_naive() - timedelta(minutes=self.RECENT_COMPLETION_MINUTES)

        async with self.mono_svc.db.session() as session:
            pending_label = func.sum(case((SQLAJob.status == JobStatus.PENDING, 1), else_=0)).label(
                "pending_count"
            )
            running_label = func.sum(case((SQLAJob.status == JobStatus.RUNNING, 1), else_=0)).label(
                "running_count"
            )
            completed_label = func.sum(
                case((SQLAJob.status == JobStatus.COMPLETED, 1), else_=0)
            ).label("completed_count")
            recent_completed_label = func.sum(
                case(
                    (
                        and_(
                            SQLAJob.status == JobStatus.COMPLETED,
                            SQLAJob.created_at >= recent_cutoff,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("recent_completed_count")
            recent_added_label = func.sum(
                case(
                    (
                        SQLAJob.created_at >= recent_cutoff,
                        1,
                    ),
                    else_=0,
                )
            ).label("recent_added_count")

            stmt = (
                select(
                    SQLAJob.type,
                    pending_label,
                    running_label,
                    completed_label,
                    recent_completed_label,
                    recent_added_label,
                )
                .where(SQLAJob.type.in_(job_types))
                .group_by(SQLAJob.type)
            )
            result = await session.execute(stmt)
            records = result.fetchall()

            ingest_recent_completed = await session.scalar(
                select(func.count())
                .select_from(SQLATelemetryAccumulation)
                .where(
                    SQLATelemetryAccumulation.data_type == "ingestion-status",
                    SQLATelemetryAccumulation.data["status"].astext == "processed",
                    SQLATelemetryAccumulation.created_at >= recent_cutoff,
                )
            )
            processing_recent_completed = await session.scalar(
                select(func.count())
                .select_from(SQLATelemetryAgentRunStatus)
                .where(
                    SQLATelemetryAgentRunStatus.status == TelemetryAgentRunStatus.COMPLETED.value,
                    SQLATelemetryAgentRunStatus.updated_at >= recent_cutoff,
                )
            )

        stats: dict[str, JobQueueStats] = {
            job_type: JobQueueStats(
                job_type=job_type,
                pending=0,
                running=0,
                completed=0,
                recent_completed=0,
                completion_rate_per_min=0.0,
                recent_added=0,
                recent_added_per_min=0.0,
            )
            for job_type in job_types
        }

        for record in records:
            pending = int(record.pending_count or 0)
            running = int(record.running_count or 0)
            completed = int(record.completed_count or 0)
            recent_completed = int(record.recent_completed_count or 0)
            recent_added = int(record.recent_added_count or 0)
            rate = (
                recent_completed / self.RECENT_COMPLETION_MINUTES
                if self.RECENT_COMPLETION_MINUTES > 0
                else 0.0
            )
            add_rate = (
                recent_added / self.RECENT_COMPLETION_MINUTES
                if self.RECENT_COMPLETION_MINUTES > 0
                else 0.0
            )
            stats[record.type] = JobQueueStats(
                job_type=record.type,
                pending=pending,
                running=running,
                completed=completed,
                recent_completed=recent_completed,
                completion_rate_per_min=rate,
                recent_added=recent_added,
                recent_added_per_min=add_rate,
            )

        if ingest_recent_completed is not None:
            count_val = int(ingest_recent_completed)
            ingest_stats = stats[WorkerFunction.TELEMETRY_INGEST_JOB.value]
            ingest_stats.recent_completed = max(ingest_stats.recent_completed, count_val)
            ingest_stats.completion_rate_per_min = (
                ingest_stats.recent_completed / self.RECENT_COMPLETION_MINUTES
                if self.RECENT_COMPLETION_MINUTES > 0
                else 0.0
            )

        if processing_recent_completed is not None:
            count_val = int(processing_recent_completed)
            processing_stats = stats[WorkerFunction.TELEMETRY_PROCESSING_JOB.value]
            processing_stats.recent_completed = max(processing_stats.recent_completed, count_val)
            processing_stats.completion_rate_per_min = (
                processing_stats.recent_completed / self.RECENT_COMPLETION_MINUTES
                if self.RECENT_COMPLETION_MINUTES > 0
                else 0.0
            )

        self._log_if_slow("fetch_job_stats", started, count=len(records))
        return stats

    def _log_if_slow(self, label: str, started: float, **details: Any) -> None:
        elapsed = perf_counter() - started
        if elapsed >= self.SLOW_QUERY_SECONDS:
            details_str = " ".join(f"{k}={v}" for k, v in details.items())
            self._logger.warning("%s took %.3fs %s", label, elapsed, details_str)

    async def fetch_jobs(self, limit: int = 50) -> list[JobInfo]:
        started = perf_counter()
        job_types = [
            WorkerFunction.TELEMETRY_PROCESSING_JOB.value,
            WorkerFunction.TELEMETRY_INGEST_JOB.value,
        ]
        async with self.mono_svc.db.session() as session:
            stmt = (
                select(SQLAJob)
                .where(SQLAJob.type.in_(job_types))
                .order_by(SQLAJob.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            jobs = result.scalars().all()
        self._log_if_slow("fetch_jobs", started, count=len(jobs))

        job_infos: list[JobInfo] = []
        for job in jobs:
            job_json: Mapping[str, Any] = job.job_json or {}
            status_value = (
                job.status.value if isinstance(job.status, JobStatus) else str(job.status)
            )
            collection_id = job_json.get("collection_id")
            log_id = job_json.get("telemetry_log_id") or job_json.get("log_id")
            job_infos.append(
                JobInfo(
                    id=job.id,
                    type=job.type,
                    status=status_value,
                    created_at=job.created_at,
                    collection_id=str(collection_id) if collection_id else None,
                    telemetry_log_id=str(log_id) if log_id else None,
                    user_email=(
                        str(job_json.get("user_email")) if job_json.get("user_email") else None
                    ),
                    payload=job_json,
                )
            )
        return job_infos

    async def fetch_completed_jobs(self, limit: int = 50) -> list[JobInfo]:
        started = perf_counter()
        job_types = [
            WorkerFunction.TELEMETRY_PROCESSING_JOB.value,
            WorkerFunction.TELEMETRY_INGEST_JOB.value,
        ]
        async with self.mono_svc.db.session() as session:
            stmt = (
                select(SQLAJob)
                .where(
                    SQLAJob.type.in_(job_types),
                    SQLAJob.status == JobStatus.COMPLETED,
                )
                .order_by(SQLAJob.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            jobs = result.scalars().all()
        self._log_if_slow("fetch_completed_jobs", started, count=len(jobs))

        job_infos: list[JobInfo] = []
        for job in jobs:
            job_json: Mapping[str, Any] = job.job_json or {}
            status_value = (
                job.status.value if isinstance(job.status, JobStatus) else str(job.status)
            )
            collection_id = job_json.get("collection_id")
            log_id = job_json.get("telemetry_log_id") or job_json.get("log_id")
            job_infos.append(
                JobInfo(
                    id=job.id,
                    type=job.type,
                    status=status_value,
                    created_at=job.created_at,
                    collection_id=str(collection_id) if collection_id else None,
                    telemetry_log_id=str(log_id) if log_id else None,
                    user_email=(
                        str(job_json.get("user_email")) if job_json.get("user_email") else None
                    ),
                    payload=job_json,
                )
            )
        return job_infos

    async def fetch_collection_statuses(self) -> list[CollectionStatusRow]:
        started = perf_counter()
        async with self.mono_svc.db.session() as session:
            statuses = SQLATelemetryAgentRunStatus
            needs_case = _telemetry_needs_work_case()
            awaiting_label = func.sum(needs_case).label("awaiting_count")
            processing_label = func.sum(
                case((statuses.status == TelemetryAgentRunStatus.PROCESSING.value, 1), else_=0)
            ).label("processing_count")
            completed_label = func.sum(
                case((statuses.status == TelemetryAgentRunStatus.COMPLETED.value, 1), else_=0)
            ).label("completed_count")
            errored_label = func.sum(
                case((statuses.status == TelemetryAgentRunStatus.ERROR.value, 1), else_=0)
            ).label("errored_count")

            recent_cutoff = utcnow_naive() - timedelta(minutes=self.RECENT_COMPLETION_MINUTES)
            recent_completed_label = func.sum(
                _telemetry_recent_completion_case(recent_cutoff)
            ).label("recent_completed")
            last_completed_label = func.max(
                case(
                    (
                        statuses.status == TelemetryAgentRunStatus.COMPLETED.value,
                        statuses.updated_at,
                    ),
                    else_=None,
                )
            ).label("last_completed_at")
            last_updated_label = func.max(statuses.updated_at).label("last_updated_at")

            stmt = (
                select(
                    statuses.collection_id,
                    awaiting_label,
                    processing_label,
                    completed_label,
                    errored_label,
                    func.count().label("total_count"),
                    recent_completed_label,
                    last_completed_label,
                    last_updated_label,
                )
                .group_by(statuses.collection_id)
                .order_by(
                    awaiting_label.desc(), processing_label.desc(), statuses.collection_id.asc()
                )
            )
            result = await session.execute(stmt)
            records = result.fetchall()
        self._log_if_slow("fetch_collection_statuses", started, count=len(records))

        rows: list[CollectionStatusRow] = []
        for record in records:
            awaiting = int(record.awaiting_count or 0)
            processing = int(record.processing_count or 0)
            completed = int(record.completed_count or 0)
            errored = int(record.errored_count or 0)
            total = int(record.total_count or 0)
            recent_completed = int(record.recent_completed or 0)
            rate = (
                recent_completed / self.RECENT_COMPLETION_MINUTES
                if self.RECENT_COMPLETION_MINUTES > 0
                else 0.0
            )
            rows.append(
                CollectionStatusRow(
                    collection_id=record.collection_id,
                    awaiting=awaiting,
                    processing=processing,
                    completed=completed,
                    errored=errored,
                    total=total,
                    recent_completed=recent_completed,
                    completion_rate_per_min=rate,
                    last_updated_at=record.last_updated_at,
                    last_completed_at=record.last_completed_at,
                )
            )
        return rows

    async def fetch_agent_run_statuses(
        self, collection_id: str, limit: int = 250
    ) -> list[AgentRunStatusRow]:
        started = perf_counter()
        async with self.mono_svc.db.session() as session:
            statuses = SQLATelemetryAgentRunStatus
            needs_case = _telemetry_needs_work_case()
            needs_case_labeled = needs_case.label("needs_work")
            status_priority = _status_priority_case()

            stmt = (
                select(
                    statuses.agent_run_id,
                    statuses.status,
                    statuses.current_version,
                    statuses.processed_version,
                    statuses.metadata_json,
                    statuses.updated_at,
                    needs_case_labeled,
                )
                .where(statuses.collection_id == collection_id)
                .order_by(
                    needs_case.desc(),
                    status_priority.asc(),
                    statuses.updated_at.desc(),
                )
                .limit(limit)
            )
            result = await session.execute(stmt)
            records = result.fetchall()
        self._log_if_slow(
            "fetch_agent_run_statuses", started, count=len(records), collection_id=collection_id
        )

        agent_rows: list[AgentRunStatusRow] = []
        for record in records:
            metadata: Mapping[str, Any] | None = record.metadata_json
            error_message: str | None = None
            if metadata:
                history = metadata.get("error_history")
                if isinstance(history, Sequence) and history:
                    last_entry = history[-1]
                    if isinstance(last_entry, Mapping):
                        error_val = last_entry.get("error")
                        if isinstance(error_val, str):
                            error_message = error_val
            requires_processing = bool(record.needs_work)
            agent_rows.append(
                AgentRunStatusRow(
                    agent_run_id=record.agent_run_id,
                    status=record.status,
                    current_version=int(record.current_version or 0),
                    processed_version=int(record.processed_version or 0),
                    updated_at=record.updated_at,
                    requires_processing=requires_processing,
                    error_message=error_message,
                )
            )
        return agent_rows


class FilterPrompt(ModalScreen[str | None]):
    """Simple modal prompt for collecting filter text."""

    CSS = """
    FilterPrompt {
        align: center middle;
    }

    #filter-container {
        width: 60%;
        max-width: 80;
        padding: 1 2;
        border: wide $primary;
        background: $panel;
    }

    #filter-help {
        color: $text-muted;
        padding-top: 1;
    }
    """

    def __init__(self, table_label: str, initial_value: str = "") -> None:
        super().__init__()
        self.table_label = table_label
        self.initial_value = initial_value

    def compose(self) -> ComposeResult:
        with Vertical(id="filter-container"):
            yield Static(f"Filter {self.table_label or 'table'} rows", id="filter-title")
            yield Input(placeholder="Type filter text and press Enter", id="filter-input")
            yield Static("Enter to apply · Escape to clear filter", id="filter-help")

    async def on_mount(self) -> None:
        filter_input = self.query_one("#filter-input", Input)
        filter_input.value = self.initial_value
        filter_input.cursor_position = len(self.initial_value)
        await filter_input.focus()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        await self.dismiss(event.value.strip())

    async def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            await self.dismiss(None)


class TelemetryDashboardApp(App[None]):
    """Textual dashboard showing telemetry processing progress."""

    DEFAULT_DESC_COLUMNS = {
        "jobs-table": {5},
        "ingestion-table": {4},
        "collections-table": {8},
        "runs-table": {5},
    }

    CSS = """
    Screen {
        layout: vertical;
    }

    #dashboard-title {
        padding: 1 2;
        content-align: left middle;
        text-style: bold;
    }

    #jobs-panel-left, #jobs-panel-right, #ingestion-panel, #collections-panel, #runs-panel {
        border: tall $primary;
        padding: 0 1;
    }

    #jobs-row {
        layout: horizontal;
        height: 13;
    }

    #jobs-panel-left, #jobs-panel-right {
        width: 1fr;
    }

    #jobs-panel-left DataTable, #jobs-panel-right DataTable {
        height: 1fr;
    }

    #main-panels {
        layout: horizontal;
        height: 1fr;
    }

    #ingestion-panel, #collections-panel, #runs-panel {
        width: 1fr;
    }
    #ingestion-panel {
        width: 0.8fr;
    }

    .panel-title {
        padding: 0 0 0 0;
        text-style: bold;
    }

    .panel-subtitle {
        color: $text-muted;
        padding-bottom: 0;
    }

    DataTable {
        height: 1fr;
    }

    #status-bar {
        height: 1;
        padding: 0 1;
        border: tall $surface;
        color: $text-muted;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh now"),
        ("a", "toggle_auto_refresh", "Auto refresh"),
        ("c", "copy_row", "Copy row"),
        ("f", "filter_table", "Filter rows"),
    ]

    AUTO_REFRESH_SECONDS = 5
    status_message = reactive("Connecting…")

    def __init__(self) -> None:
        super().__init__()
        self.data_provider = TelemetryDataProvider()
        self.jobs_table: DataTable | None = None
        self.completed_jobs_table: DataTable | None = None
        self.ingestion_table: DataTable | None = None
        self.collections_table: DataTable | None = None
        self.runs_table: DataTable | None = None
        self.jobs_summary: Static | None = None
        self.completed_jobs_summary: Static | None = None
        self.ingestion_summary: Static | None = None
        self.collections_summary: Static | None = None
        self.runs_summary: Static | None = None
        self.status_label: Static | None = None
        self.collection_rows: dict[str, CollectionStatusRow] = {}
        self.selected_collection_id: str | None = None
        self._refresh_lock = asyncio.Lock()
        self._runs_task: asyncio.Task[None] | None = None
        self.auto_refresh_enabled = True
        self._jobs_data: list[JobInfo] = []
        self._completed_jobs_data: list[JobInfo] = []
        self._ingestion_data: list[JobInfo] = []
        self._job_stats_data: dict[str, JobQueueStats] = {}
        self._collections_data: list[CollectionStatusRow] = []
        self._runs_data: list[AgentRunStatusRow] = []
        self._jobs_sort_state: tuple[int, bool] | None = None
        self._completed_jobs_sort_state: tuple[int, bool] | None = None
        self._ingestion_sort_state: tuple[int, bool] | None = None
        self._collections_sort_state: tuple[int, bool] | None = None
        self._runs_sort_state: tuple[int, bool] | None = None
        self._table_filters: dict[str, str] = {}

    def compose(self) -> ComposeResult:
        yield Static("Telemetry Control Room", id="dashboard-title")
        with Horizontal(id="jobs-row"):
            with Vertical(id="jobs-panel-left"):
                yield Static("Queued Jobs", classes="panel-title")
                yield Static("—", classes="panel-subtitle", id="jobs-summary")
                yield DataTable(id="jobs-table")
            with Vertical(id="jobs-panel-right"):
                yield Static("Recently Completed", classes="panel-title")
                yield Static("—", classes="panel-subtitle", id="completed-jobs-summary")
                yield DataTable(id="completed-jobs-table")
        with Horizontal(id="main-panels"):
            with Vertical(id="ingestion-panel"):
                yield Static("Ingestion", classes="panel-title")
                yield Static("—", classes="panel-subtitle", id="ingestion-summary")
                yield DataTable(id="ingestion-table")
            with Vertical(id="collections-panel"):
                yield Static("Collections", classes="panel-title")
                yield Static("—", classes="panel-subtitle", id="collections-summary")
                yield DataTable(id="collections-table")
            with Vertical(id="runs-panel"):
                yield Static("Agent Runs", classes="panel-title")
                yield Static(
                    "Select a collection to load agent runs",
                    classes="panel-subtitle",
                    id="runs-summary",
                )
                yield DataTable(id="runs-table")
        yield Static("", id="status-bar")
        yield Footer()

    async def on_mount(self) -> None:
        self.jobs_table = self.query_one("#jobs-table", DataTable)
        self.completed_jobs_table = self.query_one("#completed-jobs-table", DataTable)
        self.ingestion_table = self.query_one("#ingestion-table", DataTable)
        self.collections_table = self.query_one("#collections-table", DataTable)
        self.runs_table = self.query_one("#runs-table", DataTable)
        self.jobs_summary = self.query_one("#jobs-summary", Static)
        self.completed_jobs_summary = self.query_one("#completed-jobs-summary", Static)
        self.ingestion_summary = self.query_one("#ingestion-summary", Static)
        self.collections_summary = self.query_one("#collections-summary", Static)
        self.runs_summary = self.query_one("#runs-summary", Static)
        self.status_label = self.query_one("#status-bar", Static)
        self.watch_status_message(self.status_message)

        self.jobs_table.zebra_stripes = True
        self.completed_jobs_table.zebra_stripes = True
        self.ingestion_table.zebra_stripes = True
        self.collections_table.zebra_stripes = True
        self.runs_table.zebra_stripes = True

        self.jobs_table.cursor_type = "row"
        self.completed_jobs_table.cursor_type = "row"
        self.ingestion_table.cursor_type = "row"
        self.collections_table.cursor_type = "row"
        self.runs_table.cursor_type = "row"

        self.jobs_table.add_columns(
            "Status", "Type", "Collection", "Log ID", "User", "Age", "Job ID"
        )
        self.completed_jobs_table.add_columns(
            "Status", "Type", "Collection", "Log ID", "User", "Age", "Job ID"
        )
        self.ingestion_table.add_columns(
            "Status",
            "Log ID",
            "Collection",
            "User",
            "Age",
            "Job ID",
        )
        self.collections_table.add_columns(
            "Collection",
            "Awaiting",
            "Processing",
            "Done",
            "Errored",
            "Total",
            "Recent",
            "Recent/min",
            "Last Update",
            "Last Done",
        )
        self.runs_table.add_columns(
            "Agent Run",
            "Status",
            "Δ",
            "Current",
            "Processed",
            "Updated",
            "Error",
        )

        self.collections_table.focus()
        await self.data_provider.ensure_ready()
        await self.refresh_all()
        self.set_interval(self.AUTO_REFRESH_SECONDS, self._handle_auto_refresh)

    def watch_status_message(self, message: str) -> None:
        if self.status_label is not None:
            self.status_label.update(message)

    async def action_refresh(self) -> None:
        await self.refresh_all()

    async def action_toggle_auto_refresh(self) -> None:
        self.auto_refresh_enabled = not self.auto_refresh_enabled
        state = "enabled" if self.auto_refresh_enabled else "paused"
        self.status_message = f"Auto-refresh {state}"

    async def action_filter_table(self) -> None:
        focused = self.focused
        if not isinstance(focused, DataTable):
            self.status_message = "Focus a table before filtering"
            return
        table_id = focused.id or ""
        table_label = self._table_label(table_id)
        initial = self._table_filters.get(table_id, "")
        prompt = FilterPrompt(table_label, initial)
        result = await self.push_screen_wait(prompt)
        if result is None:
            self._table_filters.pop(table_id, None)
            self.status_message = f"Cleared filter on {table_label}"
        else:
            cleaned = result.strip()
            if cleaned:
                self._table_filters[table_id] = cleaned
                self.status_message = f"Filter '{cleaned}' applied to {table_label}"
            else:
                self._table_filters.pop(table_id, None)
                self.status_message = f"Cleared filter on {table_label}"
        self._re_render_table(table_id)

    async def action_copy_row(self) -> None:
        focused = self.focused
        if not isinstance(focused, DataTable):
            self.status_message = "Focus a table before copying"
            return
        row_key = getattr(focused, "cursor_row_key", None)
        if row_key is None:
            self.status_message = "No row selected to copy"
            return
        key_val = getattr(row_key, "value", row_key)
        payload = self._lookup_row_payload(focused.id, key_val)
        if payload is None:
            self.status_message = "Unable to copy row data"
            return
        text = json.dumps(payload, ensure_ascii=False, default=str)
        if self._copy_text(text):
            self.status_message = "Row copied to clipboard"
        else:
            self.status_message = text

    def _handle_auto_refresh(self) -> None:
        if not self.auto_refresh_enabled:
            return
        if self._refresh_lock.locked():
            return
        asyncio.create_task(self.refresh_all(from_timer=True))

    async def refresh_all(self, from_timer: bool = False) -> None:
        if self._refresh_lock.locked():
            if not from_timer:
                self.status_message = "Refresh already in progress"
            return

        async with self._refresh_lock:
            self.status_message = "Refreshing telemetry state…"
            try:
                jobs_task = asyncio.create_task(self.data_provider.fetch_jobs())
                completed_jobs_task = asyncio.create_task(self.data_provider.fetch_completed_jobs())
                job_stats_task = asyncio.create_task(self.data_provider.fetch_job_stats())
                collections_task = asyncio.create_task(
                    self.data_provider.fetch_collection_statuses()
                )
                jobs, completed_jobs, job_stats, collections = await asyncio.gather(
                    jobs_task, completed_jobs_task, job_stats_task, collections_task
                )
            except Exception as exc:
                self.status_message = f"Refresh failed: {exc}"
                raise
            self._render_jobs(jobs, job_stats)
            self._render_completed_jobs(completed_jobs)
            ingestion_jobs = [
                job for job in jobs if job.type == WorkerFunction.TELEMETRY_INGEST_JOB.value
            ]
            self._render_ingestion(ingestion_jobs)
            self._render_collections(collections)
            if self.selected_collection_id:
                self._start_agent_runs_task(self.selected_collection_id)
            self.status_message = "Telemetry state updated"

    def _render_jobs(
        self,
        jobs: Sequence[JobInfo],
        job_stats: Mapping[str, JobQueueStats] | None = None,
    ) -> None:
        assert self.jobs_table is not None and self.jobs_summary is not None
        cursor, scroll = self._capture_table_state(self.jobs_table)
        self._jobs_data = list(jobs)
        if job_stats is not None:
            self._job_stats_data = dict(job_stats)
        self.jobs_table.clear()
        sorted_jobs = self._sorted_jobs()
        now = utcnow_naive()
        table_id = "jobs-table"
        for job in sorted_jobs:
            age = humanize_timedelta(now - job.created_at)
            job_type = job.type.replace("_", " ").title()
            row_values = [
                job.status.upper(),
                job_type,
                job.collection_id or "—",
                job.telemetry_log_id or "—",
                job.user_email or "—",
                age,
                job.id,
            ]
            prepared = self._prepare_filtered_values(table_id, row_values)
            if prepared is None:
                continue
            self.jobs_table.add_row(*prepared, key=job.id)
        self.jobs_summary.update(self._build_job_summary())
        self._restore_table_state(self.jobs_table, cursor, scroll)

    def _render_completed_jobs(self, jobs: Sequence[JobInfo]) -> None:
        assert self.completed_jobs_table is not None and self.completed_jobs_summary is not None
        cursor, scroll = self._capture_table_state(self.completed_jobs_table)
        self._completed_jobs_data = list(jobs)
        self.completed_jobs_table.clear()
        sorted_jobs = self._sorted_completed_jobs()
        now = utcnow_naive()
        table_id = "completed-jobs-table"
        for job in sorted_jobs:
            age = humanize_timedelta(now - job.created_at)
            job_type = job.type.replace("_", " ").title()
            row_values = [
                job.status.upper(),
                job_type,
                job.collection_id or "—",
                job.telemetry_log_id or "—",
                job.user_email or "—",
                age,
                job.id,
            ]
            prepared = self._prepare_filtered_values(table_id, row_values)
            if prepared is None:
                continue
            self.completed_jobs_table.add_row(*prepared, key=job.id)
        self.completed_jobs_summary.update(self._build_completed_summary())
        self._restore_table_state(self.completed_jobs_table, cursor, scroll)

    def _render_ingestion(self, jobs: Sequence[JobInfo]) -> None:
        assert self.ingestion_table is not None and self.ingestion_summary is not None
        cursor, scroll = self._capture_table_state(self.ingestion_table)
        self._ingestion_data = list(jobs)
        self.ingestion_table.clear()
        ordered = self._sorted_ingestion()
        now = utcnow_naive()
        table_id = "ingestion-table"
        for job in ordered:
            age = humanize_timedelta(now - job.created_at)
            log_id = job.telemetry_log_id or job.payload.get("telemetry_log_id") or "—"
            collection = job.collection_id or job.payload.get("collection_id") or "—"
            row_values = [
                job.status.upper(),
                log_id,
                collection,
                job.user_email or "—",
                age,
                job.id,
            ]
            prepared = self._prepare_filtered_values(table_id, row_values)
            if prepared is None:
                continue
            self.ingestion_table.add_row(*prepared, key=job.id)
        self.ingestion_summary.update(self._build_ingestion_summary())
        self._restore_table_state(self.ingestion_table, cursor, scroll)

    def _build_job_summary(self) -> str:
        recent_window = self.data_provider.RECENT_COMPLETION_MINUTES
        ingest_stats = self._job_stats_data.get(WorkerFunction.TELEMETRY_INGEST_JOB.value)
        processing_stats = self._job_stats_data.get(WorkerFunction.TELEMETRY_PROCESSING_JOB.value)

        parts: list[str] = []
        if ingest_stats:
            parts.append(self._format_job_stats("Ingest", ingest_stats, recent_window))
        if processing_stats:
            parts.append(self._format_job_stats("Processing", processing_stats, recent_window))

        if parts:
            return " | ".join(parts)

        pending = sum(1 for job in self._jobs_data if job.status == JobStatus.PENDING.value)
        running = sum(1 for job in self._jobs_data if job.status == JobStatus.RUNNING.value)
        return f"{len(self._jobs_data)} jobs · {pending} pending · {running} running"

    @staticmethod
    def _format_job_stats(label: str, stats: JobQueueStats, recent_window: int) -> str:
        return (
            f"{label}: queued {stats.queued} (pending {stats.pending}, running {stats.running})"
            f" · added {stats.recent_added} in last {recent_window}m"
        )

    def _build_completed_summary(self) -> str:
        recent_window = self.data_provider.RECENT_COMPLETION_MINUTES
        ingest_stats = self._job_stats_data.get(WorkerFunction.TELEMETRY_INGEST_JOB.value)
        processing_stats = self._job_stats_data.get(WorkerFunction.TELEMETRY_PROCESSING_JOB.value)
        parts: list[str] = []
        if ingest_stats:
            parts.append(
                f"Ingest: {ingest_stats.recent_completed} in last {recent_window}m "
                f"({ingest_stats.completion_rate_per_min:.2f}/m)"
            )
        if processing_stats:
            parts.append(
                f"Processing: {processing_stats.recent_completed} in last {recent_window}m "
                f"({processing_stats.completion_rate_per_min:.2f}/m)"
            )
        if parts:
            return " | ".join(parts)
        return f"{len(self._completed_jobs_data)} recent completions"

    def _build_ingestion_summary(self) -> str:
        ingest_stats = self._job_stats_data.get(WorkerFunction.TELEMETRY_INGEST_JOB.value)
        if ingest_stats:
            rate_display = f"{ingest_stats.completion_rate_per_min:.2f}/m"
            return (
                f"{ingest_stats.queued} queued · {ingest_stats.pending} pending · "
                f"{ingest_stats.running} running · {ingest_stats.recent_completed} in last "
                f"{self.data_provider.RECENT_COMPLETION_MINUTES}m ({rate_display})"
            )
        pending = sum(1 for job in self._ingestion_data if job.status == JobStatus.PENDING.value)
        running = sum(1 for job in self._ingestion_data if job.status == JobStatus.RUNNING.value)
        return f"{len(self._ingestion_data)} jobs · {pending} pending · {running} running"

    def _lookup_row_payload(self, table_id: str | None, row_key: Any) -> Mapping[str, Any] | None:
        table_id = table_id or ""
        key_str = str(row_key)
        if table_id == "jobs-table":
            record = next((job for job in self._jobs_data if str(job.id) == key_str), None)
            if record:
                return {
                    "id": record.id,
                    "type": record.type,
                    "status": record.status,
                    "collection_id": record.collection_id,
                    "telemetry_log_id": record.telemetry_log_id,
                    "user_email": record.user_email,
                    "created_at": record.created_at,
                    "payload": record.payload,
                }
        elif table_id == "completed-jobs-table":
            record = next(
                (job for job in self._completed_jobs_data if str(job.id) == key_str), None
            )
            if record:
                return {
                    "id": record.id,
                    "type": record.type,
                    "status": record.status,
                    "collection_id": record.collection_id,
                    "telemetry_log_id": record.telemetry_log_id,
                    "user_email": record.user_email,
                    "created_at": record.created_at,
                    "payload": record.payload,
                }
        elif table_id == "ingestion-table":
            record = next((job for job in self._ingestion_data if str(job.id) == key_str), None)
            if record:
                return {
                    "id": record.id,
                    "status": record.status,
                    "telemetry_log_id": record.telemetry_log_id,
                    "collection_id": record.collection_id,
                    "user_email": record.user_email,
                    "created_at": record.created_at,
                    "payload": record.payload,
                }
        elif table_id == "collections-table":
            record = self.collection_rows.get(key_str)
            if record:
                return {
                    "collection_id": record.collection_id,
                    "awaiting": record.awaiting,
                    "processing": record.processing,
                    "completed": record.completed,
                    "errored": record.errored,
                    "total": record.total,
                    "recent_completed": record.recent_completed,
                    "completion_rate_per_min": record.completion_rate_per_min,
                    "last_completed_at": record.last_completed_at,
                }
        elif table_id == "runs-table":
            record = next(
                (run for run in self._runs_data if str(run.agent_run_id) == key_str), None
            )
            if record:
                return {
                    "agent_run_id": record.agent_run_id,
                    "status": record.status,
                    "current_version": record.current_version,
                    "processed_version": record.processed_version,
                    "updated_at": record.updated_at,
                    "requires_processing": record.requires_processing,
                    "error_message": record.error_message,
                }
        return None

    def _copy_text(self, text: str) -> bool:
        copier = getattr(self, "copy_to_clipboard", None)
        if callable(copier):
            try:
                copier(text)
                return True
            except Exception:
                pass
        app = getattr(self, "app", None)
        copier = getattr(app, "copy_to_clipboard", None)
        if callable(copier):
            try:
                copier(text)
                return True
            except Exception:
                pass
        runner = self._system_clipboard_runner()
        if runner:
            try:
                runner(text)
                return True
            except Exception:
                pass
        if self._copy_via_osc52(text):
            return True
        return False

    def _system_clipboard_runner(self) -> Callable[[str], None] | None:
        commands = [
            ("pbcopy", ["pbcopy"]),
            ("wl-copy", ["wl-copy"]),
            ("xclip", ["xclip", "-selection", "clipboard"]),
            ("clip.exe", ["clip.exe"]),
        ]
        for name, cmd in commands:
            path = shutil.which(name)
            if path:

                def runner(data: str, command=cmd):
                    proc = subprocess.Popen(command, stdin=subprocess.PIPE, close_fds=True)
                    proc.communicate(input=data.encode("utf-8"))

                return runner
        return None

    def _copy_via_osc52(self, text: str) -> bool:
        try:
            payload = base64.b64encode(text.encode("utf-8")).decode("ascii")
            osc = f"\033]52;c;{payload}\x07"
            # Avoid printing huge payloads
            if len(osc) > 200000:
                return False
            print(osc, end="", flush=True)
            return True
        except Exception:
            return False

    def _render_collections(self, collections: Sequence[CollectionStatusRow]) -> None:
        assert self.collections_table is not None and self.collections_summary is not None
        _cursor, scroll = self._capture_table_state(self.collections_table)
        previous_selection = self.selected_collection_id
        self._collections_data = list(collections)
        self.collection_rows = {row.collection_id: row for row in self._collections_data}

        self.collections_table.clear()
        ordered_rows = self._sorted_collections()
        table_id = "collections-table"
        for row in ordered_rows:
            rate_display = f"{row.completion_rate_per_min:.2f}/m" if row.recent_completed else "—"
            row_values = [
                row.collection_id,
                str(row.awaiting),
                str(row.processing),
                str(row.completed),
                str(row.errored),
                str(row.total),
                str(row.recent_completed),
                rate_display,
                format_ago(row.last_updated_at),
                format_ago(row.last_completed_at),
            ]
            prepared = self._prepare_filtered_values(table_id, row_values)
            if prepared is None:
                continue
            self.collections_table.add_row(*prepared, key=row.collection_id)

        needs_work = sum(1 for row in self._collections_data if row.needs_work)
        self.collections_summary.update(
            f"{needs_work} collections need work · tracking {len(self._collections_data)} total"
        )

        if self.selected_collection_id not in self.collection_rows:
            self.selected_collection_id = (
                self._collections_data[0].collection_id if self._collections_data else None
            )
        elif previous_selection:
            self.selected_collection_id = previous_selection

        if not self.selected_collection_id or self.collections_table.row_count == 0:
            self._clear_runs_table()
        else:
            highlighted = self._highlight_collection_row()
            if not highlighted:
                self._clear_runs_table()
        self._restore_table_state(self.collections_table, None, scroll)

    def _clear_runs_table(self) -> None:
        if self.runs_table is not None:
            self.runs_table.clear()
        if self.runs_summary is not None:
            self.runs_summary.update("Select a collection to load agent runs")
        self._runs_data = []

    def _start_agent_runs_task(self, collection_id: str) -> None:
        if not collection_id:
            return
        self.selected_collection_id = collection_id
        if self._runs_task and not self._runs_task.done():
            self._runs_task.cancel()
        self._runs_task = asyncio.create_task(self._load_agent_runs(collection_id))

    async def _load_agent_runs(self, collection_id: str) -> None:
        self.status_message = f"Loading agent runs for {collection_id}…"
        try:
            rows = await self.data_provider.fetch_agent_run_statuses(collection_id)
        except asyncio.CancelledError:  # pragma: no cover - cancellation is expected
            return
        except Exception as exc:
            self.status_message = f"Agent run fetch failed: {exc}"
            return

        if self.selected_collection_id != collection_id:
            return

        self._render_agent_runs(rows)
        self.status_message = f"Loaded {len(rows)} agent runs for {collection_id}"

    def _highlight_collection_row(self) -> bool:
        if self.collections_table is None or not self.selected_collection_id:
            return False
        try:
            row_index = self.collections_table.get_row_index(self.selected_collection_id)
        except KeyError:
            return False
        try:
            self.collections_table.cursor_coordinate = (row_index, 0)
        except Exception:
            return False
        return True

    def _render_agent_runs(self, runs: Sequence[AgentRunStatusRow]) -> None:
        assert self.runs_table is not None and self.runs_summary is not None
        cursor, scroll = self._capture_table_state(self.runs_table)
        self._runs_data = list(runs)
        self.runs_table.clear()
        ordered_rows = self._sorted_runs()
        urgent = sum(1 for row in self._runs_data if row.requires_processing)
        table_id = "runs-table"
        for row in ordered_rows:
            delta = row.current_version - row.processed_version
            delta_display = f"+{delta}" if delta >= 0 else str(delta)

            status_display = row.status.replace("_", " ").title()

            error_text = truncate(row.error_message, 80) if row.error_message else ""

            row_values = [
                row.agent_run_id,
                status_display,
                delta_display,
                str(row.current_version),
                str(row.processed_version),
                format_ago(row.updated_at),
                error_text or "—",
            ]
            prepared = self._prepare_filtered_values(table_id, row_values)
            if prepared is None:
                continue
            self.runs_table.add_row(*prepared, key=row.agent_run_id)

        self.runs_summary.update(
            f"{urgent} runs waiting · showing {len(self._runs_data)} most recent rows"
        )
        self._restore_table_state(self.runs_table, cursor, scroll)

    async def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id != "collections-table":
            return
        row_key = getattr(event.row_key, "value", event.row_key)
        collection_id = str(row_key)
        self._start_agent_runs_task(collection_id)

    async def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        table_id = event.data_table.id
        if table_id is None:
            return
        self._handle_sort_request(table_id, event.column_index)

    def _handle_sort_request(self, table_id: str, column_index: int) -> None:
        if table_id == "jobs-table":
            self._jobs_sort_state = self._next_sort_state(
                self._jobs_sort_state, column_index, table_id
            )
            self._render_jobs(self._jobs_data, self._job_stats_data)
        elif table_id == "completed-jobs-table":
            self._completed_jobs_sort_state = self._next_sort_state(
                self._completed_jobs_sort_state, column_index, table_id
            )
            self._render_completed_jobs(self._completed_jobs_data)
        elif table_id == "ingestion-table":
            self._ingestion_sort_state = self._next_sort_state(
                self._ingestion_sort_state, column_index, table_id
            )
            self._render_ingestion(self._ingestion_data)
        elif table_id == "collections-table":
            self._collections_sort_state = self._next_sort_state(
                self._collections_sort_state, column_index, table_id
            )
            self._render_collections(self._collections_data)
        elif table_id == "runs-table":
            self._runs_sort_state = self._next_sort_state(
                self._runs_sort_state, column_index, table_id
            )
            self._render_agent_runs(self._runs_data)

    def _re_render_table(self, table_id: str) -> None:
        if table_id == "jobs-table":
            self._render_jobs(self._jobs_data, self._job_stats_data)
        elif table_id == "completed-jobs-table":
            self._render_completed_jobs(self._completed_jobs_data)
        elif table_id == "ingestion-table":
            self._render_ingestion(self._ingestion_data)
        elif table_id == "collections-table":
            self._render_collections(self._collections_data)
        elif table_id == "runs-table":
            self._render_agent_runs(self._runs_data)

    def _table_label(self, table_id: str) -> str:
        label_map = {
            "jobs-table": "Queued Jobs",
            "completed-jobs-table": "Completed Jobs",
            "ingestion-table": "Ingestion",
            "collections-table": "Collections",
            "runs-table": "Agent Runs",
        }
        return label_map.get(table_id, table_id or "table")

    def _next_sort_state(
        self,
        current: tuple[int, bool] | None,
        column_index: int,
        table_id: str,
    ) -> tuple[int, bool]:
        default_desc = self.DEFAULT_DESC_COLUMNS.get(table_id, set())
        if current and current[0] == column_index:
            return (column_index, not current[1])
        return (column_index, column_index in default_desc)

    def _prepare_filtered_values(
        self,
        table_id: str,
        values: Sequence[str],
    ) -> list[str | Text] | None:
        filter_text = self._table_filters.get(table_id)
        if not filter_text:
            return list(values)
        normalized = filter_text.lower()
        if not any(normalized in value.lower() for value in values):
            return None
        return [self._highlight_value(value, filter_text) for value in values]

    @staticmethod
    def _highlight_value(value: str, filter_text: str) -> Text:
        text = Text(value)
        text.highlight_words([filter_text], case_sensitive=False, style="bold yellow")
        return text

    @staticmethod
    def _capture_table_state(
        table: DataTable | None,
    ) -> tuple[tuple[int, int] | None, Any]:
        if table is None:
            return None, None
        cursor = getattr(table, "cursor_coordinate", None)
        scroll_offset = getattr(table, "scroll_offset", None)
        return cursor, scroll_offset

    @staticmethod
    def _restore_table_state(
        table: DataTable | None,
        cursor: tuple[int, int] | None,
        scroll_offset: Any,
    ) -> None:
        if table is None:
            return
        if cursor is not None:
            row, col = cursor
            row_count = getattr(table, "row_count", None)
            if row_count is None:
                try:
                    row_count = len(table.rows)
                except Exception:
                    row_count = 0
            col_count = getattr(table, "column_count", None)
            if col_count is None:
                try:
                    col_count = len(table.columns)
                except Exception:
                    col_count = 0
            max_row = max(row_count - 1, 0)
            max_col = max(col_count - 1, 0)
            safe_row = min(row, max_row)
            safe_col = min(col, max_col)
            try:
                table.cursor_coordinate = (safe_row, safe_col)
            except Exception:
                pass
        if scroll_offset is not None:
            try:
                scroll_to = getattr(table, "scroll_to", None)
                if callable(scroll_to):
                    x = getattr(scroll_offset, "x", 0)
                    y = getattr(scroll_offset, "y", scroll_offset)
                    scroll_to(x=x, y=y, animate=False)
                elif hasattr(table, "scroll_offset"):
                    table.scroll_offset = scroll_offset
            except Exception:
                pass

    def _sorted_jobs(self) -> list[JobInfo]:
        data = list(self._jobs_data)
        if not data:
            return data
        if self._jobs_sort_state is None:
            self._jobs_sort_state = (5, True)
        column, reverse = self._jobs_sort_state
        key_func = JOB_SORT_MAP.get(column)
        if key_func is None:
            return data
        return sorted(data, key=key_func, reverse=reverse)

    def _sorted_completed_jobs(self) -> list[JobInfo]:
        data = list(self._completed_jobs_data)
        if not data:
            return data
        if self._completed_jobs_sort_state is None:
            self._completed_jobs_sort_state = (5, True)
        column, reverse = self._completed_jobs_sort_state
        key_func = JOB_SORT_MAP.get(column)
        if key_func is None:
            return data
        return sorted(data, key=key_func, reverse=reverse)

    def _sorted_ingestion(self) -> list[JobInfo]:
        data = list(self._ingestion_data)
        if not data:
            return data
        if self._ingestion_sort_state is None:
            self._ingestion_sort_state = (4, True)
        column, reverse = self._ingestion_sort_state
        key_func = INGEST_SORT_MAP.get(column)
        if key_func is None:
            return data
        return sorted(data, key=key_func, reverse=reverse)

    def _sorted_collections(self) -> list[CollectionStatusRow]:
        data = list(self._collections_data)
        if not data:
            return data
        if self._collections_sort_state is None:
            self._collections_sort_state = (8, True)
        column, reverse = self._collections_sort_state
        key_func = COLLECTION_SORT_MAP.get(column)
        if key_func is None:
            return data
        return sorted(data, key=key_func, reverse=reverse)

    def _sorted_runs(self) -> list[AgentRunStatusRow]:
        data = list(self._runs_data)
        if not data:
            return data
        if self._runs_sort_state is None:
            self._runs_sort_state = (5, True)
        column, reverse = self._runs_sort_state
        key_func = RUN_SORT_MAP.get(column)
        if key_func is None:
            return data
        return sorted(data, key=key_func, reverse=reverse)


def main() -> None:
    TelemetryDashboardApp().run()


if __name__ == "__main__":
    main()
