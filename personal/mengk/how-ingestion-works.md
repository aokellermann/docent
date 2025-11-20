# How Docent Telemetry Ingestion Works

This note walks through every component that touches telemetry ingestion: the REST entry points, the services that stage data, and the background workers that eventually materialize agent runs. Inline links point at the code so you can jump around while reading.

## 1. End-to-end timeline

1. **Clients send OTLP payloads** to `/v1/traces`, `scores`, and metadata endpoints. FastAPI handlers validate payloads, stash the raw bytes/log entries, and immediately enqueue background work while recording ingestion status updates for observability ([`trace_endpoint`](../../docent_core/docent/server/rest/telemetry.py#L158), [`_parse_json_body`](../../docent_core/docent/server/rest/telemetry.py#L84), [`_ensure_no_null_bytes`](../../docent_core/docent/server/rest/telemetry.py#L135)).
2. **TelemetryService persists the envelope** via [`store_telemetry_log`](../../docent_core/docent/services/telemetry.py#L88), ensuring a durable pointer that the ingest worker can resolve later even if the HTTP request fails mid-way.
3. **MonoService queues jobs** (`add_and_enqueue_telemetry_ingest_job` / `add_and_enqueue_telemetry_processing_job`) so CPU-heavy parsing never blocks the request thread ([`trace_endpoint`](../../docent_core/docent/server/rest/telemetry.py#L217), [`trace_done_endpoint`](../../docent_core/docent/server/rest/telemetry.py#L306)).
4. **`telemetry_ingest_job`** pops the raw OTLP payload, enforces permissions/collection existence, decodes spans, and writes normalized spans + metadata into the accumulation tables ([`telemetry_ingest_job`](../../docent_core/docent/workers/telemetry_ingest_worker.py#L38)).
5. **TelemetryAccumulationService** stores spans, scores, and metadata while atomically marking affected agent runs as “needs processing,” which increments a per-run version counter so later jobs know fresh data arrived ([`add_spans`](../../docent_core/docent/services/telemetry_accumulation.py#L149), [`_mark_agent_runs_for_processing`](../../docent_core/docent/services/telemetry_accumulation.py#L700)).
6. **`telemetry_processing_job`** repeatedly asks TelemetryService to claim agent runs that still have outstanding data, rehydrates the staged blobs, and persists rich AgentRun/Transcript structures to the main tables ([`telemetry_processing_job`](../../docent_core/docent/workers/telemetry_worker.py#L20)).
7. **Status + retry hooks**: ingestion status rows let us trace every OTLP request, and per-run versions ensure that new data causes reprocessing even if a previous run failed ([`add_ingestion_status`](../../docent_core/docent/services/telemetry_accumulation.py#L96), [`has_remaining_work`](../../docent_core/docent/services/telemetry.py#L1033)).

## 2. REST entry points & validations

* **`/v1/traces`** – Accepts OTLP protobuf payloads, enforces `application/x-protobuf`, base64-encodes the body for durable logging, and queues the ingest worker while also logging `received` / `queued` statuses for the telemetry log ([`trace_endpoint`](../../docent_core/docent/server/rest/telemetry.py#L158)).
* **`/v1/trace-done`** – Lightweight signal that forces a telemetry-processing job to run after a trace has “settled.” It verifies collection ownership and records the request for auditing ([`trace_done_endpoint`](../../docent_core/docent/server/rest/telemetry.py#L262)).
* **Scores & agent metadata** – `/v1/scores` and `/v1/agent-run-metadata` share the same pattern: validate required fields, sanity check strings for null bytes, store the log entry, append the payload to accumulation tables (scores or metadata), then queue processing ([`add_score_endpoint`](../../docent_core/docent/server/rest/telemetry.py#L325), [`add_metadata_endpoint`](../../docent_core/docent/server/rest/telemetry.py#L412)).
* **Transcript metadata** – `/v1/transcript-metadata` and `/v1/transcript-group-metadata` let clients add per-transcript context before the full run is processed. They reuse the same accumulation service so downstream processing can merge metadata chronologically ([`add_transcript_metadata_endpoint`](../../docent_core/docent/server/rest/telemetry.py#L495), [`add_transcript_group_metadata_endpoint`](../../docent_core/docent/server/rest/telemetry.py#L585)).
* **`/{collection_id}/ensure-telemetry-processing`** – When a user opens a collection, this endpoint opportunistically queues processing if any work remains (anonymous read access is allowed so even viewers can nudge backlog processing). It simply instantiates a TelemetryService and calls `ensure_telemetry_processing_for_collection` ([`ensure_telemetry_processing`](../../docent_core/docent/server/rest/telemetry.py#L682)).

All JSON endpoints use `_parse_json_body` and `_ensure_no_null_bytes` to reject malformed payloads early ([`telemetry.py`](../../docent_core/docent/server/rest/telemetry.py#L84)).

## 3. TelemetryService (core orchestrator)

### 3.1 Telemetry logging & collection enforcement

* [`store_telemetry_log`](../../docent_core/docent/services/telemetry.py#L88) creates a `SQLATelemetryLog` record so every request can be replayed later. `update_telemetry_log_collection_id` tags the log with the eventual collection once known.
* [`ensure_collections_exist`](../../docent_core/docent/services/telemetry.py#L534) + [`ensure_collection_exists`](../../docent_core/docent/services/telemetry.py#L553) wrap `MonoService` helpers to lazily create collections (and optionally update missing names) as spans arrive.
* [`ensure_write_permission_for_collections`](../../docent_core/docent/services/telemetry.py#L591) enforces that the API key belongs to a user with write access on any existing collection, but permits new collection IDs so that ingestion can create them on the fly (`ensure_write_permission_for_collection` reuses the multi-collection variant at [`#L649`](../../docent_core/docent/services/telemetry.py#L649)).

### 3.2 OTLP decoding & span normalization

* [`parse_protobuf_traces`](../../docent_core/docent/services/telemetry.py#L651) handles OTLP HTTP Collector payloads, converting the protobuf to a Python dict via `MessageToDict`.
* [`extract_spans`](../../docent_core/docent/services/telemetry.py#L676) loops through resource/spans/scope triples, merges attributes, and delegates each raw span to [`otel_span_format_to_dict`](../../docent_core/docent/services/telemetry.py#L780) which normalizes IDs (hex-encodes span/trace IDs, preserves both raw/base64 values), converts nanosecond timestamps to ISO strings, copies events/links, and retains the full original payload for debugging.
* [`extract_collection_info_from_spans`](../../docent_core/docent/services/telemetry.py#L503) reads `collection_id` from span attributes and derives default names from `resource_attributes["service.name"]`, which later drives collection creation.

### 3.3 Accumulation & work queueing

* [`accumulate_spans`](../../docent_core/docent/services/telemetry.py#L873) groups spans by collection ID, uses `TelemetryAccumulationService.add_spans` to persist them, and records which agent runs were touched so `_mark_agent_runs_for_processing` can bump their version counters.
* [`get_and_mark_agent_runs_for_processing`](../../docent_core/docent/services/telemetry.py#L921) is the heart of the queue. It orders candidate agent runs by status (needs_processing > completed_with_new_data > errored_with_new_data > fallback), claims them with `SELECT ... FOR UPDATE SKIP LOCKED`, and flips their status to `PROCESSING` while returning the `current_version` snapshot the worker is about to handle.
* [`has_remaining_work`](../../docent_core/docent/services/telemetry.py#L1033) scans for any row whose `current_version` is ahead of `processed_version` and either isn’t in an error state or has newer data than the last recorded error, so we never skip fresh telemetry.
* [`ensure_telemetry_processing_for_collection`](../../docent_core/docent/services/telemetry.py#L1085) ties it together by checking `has_remaining_work` and queuing a processing job if needed.

### 3.4 Agent-run processing & persistence

* [`process_agent_runs_for_collection`](../../docent_core/docent/services/telemetry.py#L155) drives the worker loop. It claims batches of agent runs, grabs a Redis lock per `(collection_id, agent_run_id)` to avoid double processing across workers, and tracks timing metrics.
* [`_process_single_agent_run`](../../docent_core/docent/services/telemetry.py#L378) fetches staged spans/scores/metadata from TelemetryAccumulationService (`get_agent_run_spans`, `get_agent_run_scores`, `get_agent_run_metadata`, `get_agent_run_transcript_group_metadata`), normalizes spans into transcript buckets (assigning a default transcript if spans lack IDs), and optionally converts transcript group metadata via [`_create_transcript_groups_from_accumulation_data`](../../docent_core/docent/services/telemetry.py#L1681).
* [`_create_agent_runs_from_spans`](../../docent_core/docent/services/telemetry.py#L1734) builds `AgentRun` objects: it walks each transcript’s spans, extracts chat messages + tool events, folds in accumulated scores/metadata, and prepares transcript group hierarchies so the downstream persistence layer can rebuild the conversation tree.
* [`update_agent_runs_for_telemetry`](../../docent_core/docent/services/telemetry.py#L1250) persists the result. It checks space quotas, upserts `SQLAAgentRun` rows, deletes & recreates transcripts, validates transcript group parents, and sorts groups so ancestors are inserted before children (`sort_transcript_groups_by_parent_order`).
* After a run completes, `_mark_agent_runs_as_completed` advances `processed_version` (ensuring it never regresses even if someone else updated the row) and logs successes, while `_mark_agent_runs_as_errored` captures error metadata/history if transformation fails ([`_mark_agent_runs_as_completed`](../../docent_core/docent/services/telemetry.py#L1113), [`_mark_agent_runs_as_errored`](../../docent_core/docent/services/telemetry.py#L1164)).

## 4. TelemetryAccumulationService (staging area)

* Keys follow `collection_id=...:agent_run_id=...:transcript_group_id=...:transcript_id=...` so all partial artifacts for the same run sort next to each other ([`_build_key`](../../docent_core/docent/services/telemetry_accumulation.py#L48)). `_escape_like_pattern` lets us query by prefix using SQL LIKE safely.
* [`add_ingestion_status`](../../docent_core/docent/services/telemetry_accumulation.py#L96) writes status records keyed by telemetry log ID so we can see every phase (“received”, “processing”, “processed”, “failed”). `get_latest_ingestion_status` powers ingest-worker deduping.
* [`add_spans`](../../docent_core/docent/services/telemetry_accumulation.py#L149) stores each normalized span as JSON, tracks which agent runs were touched, and calls `_mark_agent_runs_for_processing` to bump `current_version`. If spans lacked `agent_run_id`, they still get stored (keyed by collection only) but won’t trigger reprocessing.
* Score + metadata helpers (`add_score`, `add_agent_run_metadata`, `add_transcript_metadata`, `add_transcript_group_metadata`) append structured rows sorted by timestamp, letting downstream processing merge repeated calls deterministically ([`add_score`](../../docent_core/docent/services/telemetry_accumulation.py#L247), [`add_agent_run_metadata`](../../docent_core/docent/services/telemetry_accumulation.py#L347), [`add_transcript_metadata`](../../docent_core/docent/services/telemetry_accumulation.py#L402), [`add_transcript_group_metadata`](../../docent_core/docent/services/telemetry_accumulation.py#L444)). Transcript-group metadata uses `deep_merge_dicts` so later calls can append nested fields without clobbering earlier ones ([`deep_merge_dicts`](../../docent_core/docent/services/telemetry_accumulation.py#L26)).
* Retrieval helpers (`get_agent_run_spans`, `get_agent_run_scores`, `get_agent_run_metadata`, `get_agent_run_transcript_group_metadata`) order entries by `created_at` or timestamp so `_process_single_agent_run` can replay them chronologically ([`get_agent_run_spans`](../../docent_core/docent/services/telemetry_accumulation.py#L219)).
* Cleanup helpers (`delete_accumulation_data`, `delete_agent_run_accumulations`) let us purge staging rows after successful processing or if collection/agent run data needs to be reingested ([`delete_accumulation_data`](../../docent_core/docent/services/telemetry_accumulation.py#L624)).

## 5. Background workers

### 5.1 `telemetry_ingest_job`

* Resolves the user (so we have the right permission context) and grabs a Redis lock keyed by telemetry log to avoid double-processing if a job is retried ([`telemetry_ingest_worker.py`](../../docent_core/docent/workers/telemetry_ingest_worker.py#L52)).
* Short-circuits if the latest ingestion status is already “processed,” making retries idempotent ([`#L99`](../../docent_core/docent/workers/telemetry_ingest_worker.py#L99)).
* Fetches the log, marks it `processing`, decodes + decompresses the payload via `_decode_body`, and falls back to legacy JSON logs if necessary ([`_decode_body`](../../docent_core/docent/workers/telemetry_ingest_worker.py#L25), [`telemetry_ingest_job`](../../docent_core/docent/workers/telemetry_ingest_worker.py#L121)).
* Parses spans, enforces that the user can write to every collection ID encoded in the spans, lazily creates missing collections, and associates the telemetry log with the primary collection ([`#L149-191`](../../docent_core/docent/workers/telemetry_ingest_worker.py#L149)).
* Calls `TelemetryService.accumulate_spans`, then queues a telemetry-processing job per collection so downstream work gets scheduled even if multiple collections share the same OTLP payload ([`#L200-229`](../../docent_core/docent/workers/telemetry_ingest_worker.py#L200)).
* Writes a final `processed` or `failed` ingestion status with timing info so the UI/logs can show progress ([`#L230-267`](../../docent_core/docent/workers/telemetry_ingest_worker.py#L230)).

### 5.2 `telemetry_processing_job`

* Resolves the user, instantiates TelemetryService, and calls `process_agent_runs_for_collection` with guardrails (limit=10, `time_budget_seconds` ≈ half the worker timeout) so runs don’t overrun the job slot ([`telemetry_worker.py`](../../docent_core/docent/workers/telemetry_worker.py#L60)).
* After each batch it immediately calls `ensure_telemetry_processing_for_collection` to see if more work remains; if yes, a new job is queued before the current one exits, guaranteeing at-least-once processing until backlog drains ([`telemetry_worker.py`](../../docent_core/docent/workers/telemetry_worker.py#L86)).

## 6. Failure handling & observability

* **Ingestion status trail** – Every `/v1/traces` call writes `received`, the ingest worker writes `processing` and `processed` (including counts, request IDs, elapsed time, `compat_mode`), and any exception records `failed` with the error string ([`trace_endpoint`](../../docent_core/docent/server/rest/telemetry.py#L205), [`telemetry_ingest_job`](../../docent_core/docent/workers/telemetry_ingest_worker.py#L123), [`telemetry_ingest_job` failure handler](../../docent_core/docent/workers/telemetry_ingest_worker.py#L251)).
* **Per-agent-run versions** – `TelemetryAccumulationService._mark_agent_runs_for_processing` bumps `current_version` every time new spans/scores/metadata arrive, `get_and_mark_agent_runs_for_processing` records which version was processed, and `_mark_agent_runs_as_completed`/`_mark_agent_runs_as_errored` compare the stored version to decide whether to retry or surface errors ([`get_and_mark_agent_runs_for_processing`](../../docent_core/docent/services/telemetry.py#L921), [`_mark_agent_runs_as_errored`](../../docent_core/docent/services/telemetry.py#L1164)).
* **Locking + skip-locked selects** – Redis locks in `process_agent_runs_for_collection` serialize per-run work, while `SELECT ... FOR UPDATE SKIP LOCKED` lets multiple workers drain the backlog without deadlocking each other ([`process_agent_runs_for_collection`](../../docent_core/docent/services/telemetry.py#L155), [`get_and_mark_agent_runs_for_processing`](../../docent_core/docent/services/telemetry.py#L921)).
* **User-level permissions** – Both the REST handlers and ingest worker reuse `ensure_collection_exists` and `ensure_write_permission_for_collections`, so even background retries always run as the originating user and respect ACLs ([`trace_endpoint`](../../docent_core/docent/server/rest/telemetry.py#L290), [`telemetry_ingest_job`](../../docent_core/docent/workers/telemetry_ingest_worker.py#L149)).
* **Manual nudges** – `/v1/trace-done` and `/ensure-telemetry-processing` give us hooks to poke the pipeline whenever UI interactions or external orchestration detect stale data.

Together these pieces let Docent accept arbitrary OTLP telemetry, enrich it with human annotations (scores/metadata), and reliably materialize agent-run records even if ingestion is bursty or partially failing.
