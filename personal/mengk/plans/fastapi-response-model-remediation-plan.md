# FastAPI Response-Model Remediation Plan for `docent_core/docent/server/rest`

## Summary
Normalize REST endpoints to use Pydantic return type annotations (instead of decorator `response_model=`) and add missing Pydantic response models for stable JSON payloads, while preserving current runtime behavior for streaming, telemetry header responses, null-body endpoints, and truly dynamic payloads.

## Scope and Defaults (Locked)
- `Scope`: **Hybrid**
- `Null-body policy`: **Preserve existing null responses**
- `Telemetry policy`: **Keep explicit `JSONResponse` behavior with `x-docent-request-id`**
- `No behavior changes`: keep response shapes/status codes unchanged unless needed to express an existing stable payload with a model.
- `Model locality`: define response `BaseModel` classes close to usage. If used once, place directly above that endpoint. If shared, place above the first endpoint that uses it (not grouped at file top).

## Implementation Plan

## 1. Build a deterministic endpoint inventory gate (non-runtime helper script, not committed)
Use the same AST-based scan approach used in planning to classify every endpoint into:
1. `decorator_response_model`
2. `already_pydantic_return_annotation`
3. `stable_json_needs_model`
4. `dynamic_or_streaming_or_null_exempt`

This gate is used before/after edits to prove all endpoints were reviewed.

## 2. Convert all decorator `response_model=` uses to return annotations
Edit all 24 current decorator-based endpoints so:
- `@router.<verb>(..., response_model=T)` -> `@router.<verb>(...)`
- function signature `-> T`
- keep all other decorator args unchanged (`status_code`, etc.)

Files:
- `docent_core/docent/server/rest/code_samples.py`
- `docent_core/docent/server/rest/settings.py`
- `docent_core/docent/server/rest/router.py`
- `docent_core/docent/server/rest/rubric.py`

## 3. Add/upgrade Pydantic response models for stable JSON endpoints
Create local response models in each module (preferred over cross-module shared file to reduce coupling), then annotate endpoints accordingly.
Placement rule for readability:
- Avoid centralizing all response models at the top of the file.
- Single-use models go immediately above their endpoint.
- Multi-use models go above the first endpoint that uses them.

Planned model additions by file:

- `docent_core/docent/server/rest/chart.py`
  - `ChartCreateResponse` (`id`)
  - `StatusResponse` (`status`)
  - Apply to `create_chart`, `update_chart`, `delete_chart`

- `docent_core/docent/server/rest/chat.py`
  - `SessionIdResponse` (`session_id`)
  - `ActiveJobResponse` (`job_id: str | None`)
  - `MessageResponse` (`message`)
  - Apply to `create_session`, `create_followup_from_result`, `create_collection_conversation`, `create_conversation`, `get_active_chat_job_for_session`, `get_active_conversation_job`, `delete_conversation`

- `docent_core/docent/server/rest/refinement.py`
  - `RefinementSessionJobResponse` (`session_id`, `rubric_id`, `job_id`)
  - `RefinementMessageResponse` (`job_id`, `rsession`)
  - `MessageResponse` (`message`)
  - Annotate:
    - `create_refinement_session` -> return `RefinementAgentSession` (via explicit `to_pydantic().prepare_for_client()` conversion)
    - `start_refinement_session`, `get_refinement_job`, `post_message_to_refinement_session`, `retry_last_message`, `post_rubric_update_to_refinement_session`, `cancel_active_refinement_message`, `get_current_state_endpoint`

- `docent_core/docent/server/rest/result_set.py`
  - `MessageResponse` (`message`)
  - `DeleteResultSetResponse` (`deleted: bool`)
  - Apply to `cancel_result_set_jobs`, `delete_result_set`

- `docent_core/docent/server/rest/rubric.py`
  - `FilterFieldsResponse` (`fields`)
  - `RubricJobDetailsResponse` (`id`, `status`, `created_at`, `total_agent_runs`) and annotate nullable return
  - `CopyRubricResponse` (`rubric_id`)
  - Reuse `StartEvalJobResponse` for job-id endpoints
  - Annotate `create_rubric`, `get_rubrics`, `get_latest_rubric_version`, `get_judge_result_filter_fields`, `cancel_job`, `start_eval_rubric_job`, `get_rubric_job_details`, `get_judge_models`, `start_clustering_job`, `copy_rubric`

- `docent_core/docent/server/rest/settings.py`
  - `UsageSummaryResponse` (`window_seconds`, `free`, `byok`)
  - `MessageResponse` (`message`)
  - Apply to `get_usage_summary`, `delete_model_api_key`

- `docent_core/docent/server/rest/label.py`
  - `MessageResponse` (`message`)
  - Convert all `dict[str, str]` success endpoints to `MessageResponse`

- `docent_core/docent/server/rest/data_table.py`
  - `MessageResponse` (`message`)
  - Apply to `delete_data_table`

- `docent_core/docent/server/rest/router.py`
  - Add focused response models for stable dict literals, including:
    - auth/session responses (`signup`, `login`, `anonymous_session`)
    - ping/status/message responses
    - collection/job/filter action payloads (`create_collection`, `clone_collection`, `delete_filter`, etc.)
    - API-key test/disable payloads
  - Annotate existing Pydantic-returning endpoints that currently lack return annotations (e.g., collaborators/org user endpoints, filter endpoints already returning model objects).

## 4. Explicit exemption list (kept unchanged intentionally)
Do not force BaseModel return annotations for:
- Streaming endpoints returning `StreamingResponse`
- Telemetry endpoints that use `_success_response(JSONResponse)` for request-id headers
- Endpoints that intentionally return no body (`None`)
- Truly dynamic payload endpoints where response keys/schema are intentionally open (`dict[str, Any]` style metadata/preview payloads)

## 5. Validation and quality gates
After edits:
1. `ruff format`
2. `pyright`
3. Verification scans:
   - `rg -n "response_model\\s*=" docent_core/docent/server/rest/*.py` -> expected none
   - rerun endpoint classification script -> all non-exempt endpoints should be in `already_pydantic_return_annotation`

## Public Interface/Type Changes
- OpenAPI generation will come from function return annotations rather than decorator `response_model=`.
- New named response models will appear in schema components for previously anonymous dict payloads.
- HTTP payloads remain same shape (except only where required to faithfully model existing stable payloads; no intentional schema-breaking reshapes).

## Test Scenarios
1. Each converted endpoint returns the same JSON keys/values as before (spot-check per file group).
2. Streaming endpoints still stream SSE unchanged.
3. Telemetry endpoints still include `x-docent-request-id` on success and error.
4. Null-body endpoints still return null/no body semantics as before.
5. OpenAPI docs reflect return annotation types for formerly `response_model=` routes.

## Assumptions
- Existing Pydantic/domain models used in annotations are valid serialization targets in current FastAPI/Pydantic setup.
- Dynamic metadata endpoints are intentionally schema-flexible and are excluded by design under the selected Hybrid policy.
- No frontend/API contract consumers depend on OpenAPI component names for former ad-hoc dict responses.
