# Agent Run Compression Plan

## Goal
- Reduce upload time and bandwidth when ingesting large batches of `AgentRun` objects via `/rest/{collection_id}/agent_runs` without breaking existing clients.
- Re-use standard HTTP compression primitives (start with `gzip`) so we do not need an out-of-band packaging format.

## Context
- Client uploads are initiated via `Docent.add_agent_runs` (`docent/docent/sdk/client.py`) which currently sends plain JSON batches to `/rest/{collection_id}/agent_runs`.
- Server ingestion lives in `docent_core/docent/server/rest/router.py` (FastAPI). The `post_agent_runs` endpoint takes a `PostAgentRunsRequest` body and forwards to `MonoService.add_agent_runs` (`docent_core/docent/services/monoservice.py`).
- Only the router needs to know how to decompress; `MonoService` already operates on Python objects and should remain agnostic.

## Implementation Steps
1. **Server request parsing**
   - Update the `/agent_runs` endpoint to accept a raw `Request` plus the optional `Content-Encoding` header.
   - When `Content-Encoding: gzip`, read the byte body once, decompress via `gzip.decompress`, and `json.loads` the result before validating with `PostAgentRunsRequest.model_validate`.
   - Preserve the existing JSON body path when no encoding header is present. Return `HTTP 415/400` for unsupported encodings or malformed compressed payloads.
   - Keep existing permission checks, analytics, and `MonoService.add_agent_runs` call untouched; just pass the parsed `agent_runs` list onward.

2. **Client compression toggle**
   - Extend `Docent.add_agent_runs` with a `compression` parameter (e.g., `Literal["gzip", "none"]`, default `"gzip"`).
   - Serialize each batch once via `json.dumps`. When compression is enabled, compress bytes using `gzip` and send the request with `data=` plus headers `Content-Type: application/json` and `Content-Encoding: gzip`; otherwise fall back to the existing `json=` code path.
   - Optionally allow callers to disable compression (or future algorithms) without code changes. If the server rejects compressed uploads, surface the error so callers can retry uncompressed.

3. **Telemetry/observability**
   - Add structured logging or metrics when compressed payloads are used (e.g., log compression ratio) so we can validate impact in production.
   - Ensure any analytics events still report the number of ingested runs regardless of encoding.

4. **Testing**
   - FastAPI tests: add a case (probably alongside `tests/integration/test_charts.py`) that sends a gzip-compressed request body to `/agent_runs` and asserts the runs land in the DB.
   - SDK tests: stub `requests.Session.post` (or use `requests_mock`) to verify the client sets `Content-Encoding: gzip` and transmits compressed bytes when the option is enabled, and that disabling compression maintains current behavior.
   - Regression tests for error handling: invalid gzip data yields a 400 with a helpful message.

5. **Documentation & rollout**
   - Mention the new compression support in the SDK docstring / README snippet so users know uploads are compressed by default and how to disable or change algorithms.
   - Coordinate deployment so the server change ships before (or simultaneously with) the SDK default switch to compression.
