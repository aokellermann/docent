# Agent Run Size-Based Batching Plan

## Goal
- Ensure every POST to `/rest/{collection_id}/agent_runs` stays under the backend's 50 MB payload cap.
- Replace the current fixed-count chunking in `docent/docent/sdk/client.py` with batches that respect serialized request size, while keeping compression support transparent to callers.

## Context
- `Docent.add_agent_runs` previously chunked solely by `_batch_size`; the new design will chunk strictly by serialized payload size so callers no longer tune a count-based parameter.
- The backend limit applies to the actual HTTP body (after optional compression). We need to prepare batches whose serialized bytes (and, when compressed, their compressed bytes) do not exceed 50 MB.
- Agent runs vary in size, so fixed-count batching can still exceed 50 MB when runs contain large transcripts/artifacts.

## Implementation Steps
1. **Understand current batching flow**
   - Review `Docent.add_agent_runs` to note where `_chunked(agent_runs, batch_size)` is called, how payloads are serialized, and where compression is applied.
   - Identify a hook to replace the simple chunking loop with a size-aware generator that yields batches plus their serialized bytes.

2. **Introduce size-aware chunker**
   - Implement `_yield_batches_by_size(runs, max_payload_bytes, serializer)` that streams through `agent_runs` and keeps an accumulator: `current_runs`, `current_body_bytes`, and optionally the already-serialized body blob. The helper should:
     - Serialize each candidate run once via `serializer(run)` (e.g., returning the UTF-8 bytes for the JSON snippet) and store both the Python object and the bytes.
     - Track size using `len(body_prefix) + len(run_bytes)` where `body_prefix` includes `[{"agent_runs":` wrapper, commas between runs, and closing `]}`. We can maintain counters for `envelope_bytes = len('{"agent_runs":[')` + len(']}')` and per-comma overhead (=1) to avoid recomputing strings.
     - When adding a run would exceed `max_payload_bytes`, yield the current batch along with the already-built bytes blob (or the list of `run_bytes` so the caller can assemble `b'{"agent_runs":[' + b','.join(...) + b']}'`). Reset accumulators and continue.
     - If a single run alone is > `max_payload_bytes`, raise `ValueError` so callers know the run must be split/trimmed.
   - Favor building the final JSON bytes inside the helper to avoid `json.dumps` rework in the caller: e.g., maintain `bytearray` and append `run_bytes` plus comma delimiters.
   - For compression, take the conservative approach: enforce the 50 MB limit on the uncompressed JSON body (ensuring we never hit server size checks regardless of compression) and then optionally compress the final bytes before sending. Capture stats (size before/after) for logging so we know actual transfer sizes.

3. **Integrate with request sending**
   - Replace `_chunked` loop (and eventually drop the `batch_size` argument) with the size-aware generator, yielding `(batch_runs, serialized_body_bytes)` so we can hand off to the existing compression logic without re-dumping JSON multiple times.
   - Enforce `max_payload_bytes = 50 * 1024 * 1024`. If a single run exceeds the limit by itself, raise a descriptive error before attempting the upload.
   - Maintain existing retry/backoff and logging; log when batches are split due to size to aid debugging.

4. **Testing & validation**
   - Extend/adjust SDK unit tests to cover:
     - Batches split based on size rather than count (e.g., configure batch size limit small and verify number of POSTs).
     - Exact-boundary behavior (contents exactly 50 MB, 50 MB + 1 byte).
     - Error raised when a single run exceeds limit.
     - Interplay with compression path (ensures helper still feeds compressed uploads).
   - Optionally add integration test (mock server) verifying request bodies respect limit.

5. **Documentation & rollout**
   - Update SDK docstrings/README to mention size-based batching and the 50 MB constraint.
   - Communicate change to teams relying on `_batch_size` so they know the numeric parameter has been removed in favor of automatic size-based chunking.
