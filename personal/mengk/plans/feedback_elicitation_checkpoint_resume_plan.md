# Plan: Add checkpointing + resume to feedback_elicitation.py

## 1) Goal / Restatement
Implement checkpointing and resume support in `personal/mengk/rubric_elicit/feedback_elicitation.py`, mirroring the approach in `personal/mengk/rubric_elicit/elicit_ambiguities.py`. This includes:
- Saving pipeline state after each step.
- Resuming from a checkpoint at a specified iteration.step (`--resume-step`).
- Reusing agent_run_ids from a checkpoint instead of re-sampling.
- Truncating stale iteration history when resuming earlier than the latest iteration.
- Capturing enough state so the pipeline can resume without redoing completed steps.

## 2) Relevant Codebase Findings (self-contained)

### 2.1 feedback_elicitation pipeline and structure
File: `personal/mengk/rubric_elicit/feedback_elicitation.py`

`run_feedback_elicitation` currently:
- Initializes clients and samples agent runs once.
- Creates `UserData` and `UserModel` from the initial rubric.
- Iterates up to `max_iterations` and runs the steps inline, without checkpointing.

Key step flow (excerpted, simplified):
```python
for iteration in range(1, max_iterations + 1):
    current_rubric_text = user_model.model_text

    # Step 1: extract
    extracted_questions = await extract_questions_from_agent_runs(...)

    # Step 2: dedup
    sorted_questions = sort_questions_by_novelty(extracted_questions)
    selected_questions, dedup_metadata = await deduplicate_and_select_questions(...)

    if not selected_questions: break

    # Step 3: collect answers
    user_answers = collect_interactive_answers(selected_questions, dedup_metadata)
    if not user_answers: break

    # Step 4: update UserData
    for answer in user_answers: user_data.add_qa_pair(...)

    # Step 5: update UserModel
    new_model_text = await update_user_model(...)
    user_model.update_model(new_model_text)

    # Step 6: analyze decomposition (prototype, interactive)
    decomposition = await analyze_rubric_decomposition(...)
    if decomposition: ... prompt for feedback ...
```

There is no checkpointing or resume support in this file. CLI options do not include `--resume` or `--resume-step`.

### 2.2 User data/model are Pydantic BaseModels
File: `docent_core/docent/ai_tools/rubric/user_model.py`

`UserData` and `UserModel` are Pydantic models, which makes them JSON-serializable via `model_dump()` and loadable via `model_validate()`:
```python
class UserData(BaseModel):
    initial_rubric: str
    qa_pairs: list[QAPair] = Field(default_factory=lambda: list[QAPair]())
    labels: list[LabeledRun] = Field(default_factory=lambda: list[LabeledRun]())
    created_at: datetime = Field(default_factory=datetime.now)
    last_updated: datetime = Field(default_factory=datetime.now)

class UserModel(BaseModel):
    model_text: str
    version: int = 1
    user_data: UserData
    created_at: datetime = Field(default_factory=datetime.now)
    last_updated: datetime = Field(default_factory=datetime.now)
```

### 2.3 Checkpointing pattern in elicit_ambiguities.py (to mirror)
File: `personal/mengk/rubric_elicit/elicit_ambiguities.py`

Checkpointing is implemented with:
- `IterationState` and `PipelineCheckpoint` Pydantic models.
- `save_checkpoint`, `load_checkpoint`, `create_checkpoint_path` helpers.
- `parse_resume_step`, `validate_resume_state`, `get_resume_state` to validate `--resume-step`.
- `save_step_checkpoint` that writes a checkpoint after each step.
- Resume logic that truncates iteration history if resuming earlier than the latest iteration.

Relevant excerpts (simplified):
```python
class IterationState(BaseModel):
    iteration: int
    rubric_text: str
    rubric_version: int
    current_step: int = 0
    extracted_questions: list[ElicitedQuestion] | None = None
    selected_questions: list[ElicitedQuestion] | None = None
    dedup_metadata: dict[str, Any] | None = None
    user_answers: list[UserAnswerWithContext] | None = None
    bottleneck_results: list[BottleneckExtractionResult] | None = None
    aggregated_result: AggregatedRubricResult | None = None

class PipelineCheckpoint(BaseModel):
    created_at: datetime
    last_updated: datetime
    collection_id: str
    rubric_description: str
    num_samples: int
    max_questions: int
    max_iterations: int = 10
    agent_run_ids: list[str] | None = None
    current_iteration: int = 0
    current_step: int = 0
    iteration_history: list[IterationState] = []
    final_rubric_text: str | None = None
    final_rubric_version: int | None = None
    convergence_reason: str | None = None
```

Resume handling in `run_elicitation`:
```python
if resume_from:
    checkpoint = load_checkpoint(resume_from)
    if checkpoint.collection_id != collection_id: raise ValueError(...)
    if checkpoint.rubric_description != rubric_description:
        print("Warning... Using checkpoint version.")
        rubric_description = checkpoint.rubric_description
    if checkpoint.max_iterations != max_iterations: ...
    if not resume_step: raise ValueError("--resume-step is required...")
else:
    checkpoint_path = create_checkpoint_path(collection_id)
    checkpoint = PipelineCheckpoint(...)

# agent runs:
if resume_from and checkpoint.agent_run_ids: fetch runs by id, validate >= 10
else: sample runs, store checkpoint.agent_run_ids, save checkpoint

# resume state:
if resume_from:
    target_iteration, target_step, existing_iter_state = get_resume_state(checkpoint, resume_step)
    if target_iteration <= len(checkpoint.iteration_history):
        checkpoint.iteration_history = checkpoint.iteration_history[:target_iteration]
        checkpoint.final_rubric_text = None
        checkpoint.final_rubric_version = None
        checkpoint.convergence_reason = None
else:
    target_iteration, target_step, existing_iter_state = 1, 1, None
```

Then each step sets `iter_state` fields and calls `save_step_checkpoint` to persist after the step completes.

## 3) Proposed Approach (mirror elicit_ambiguities)

### 3.1 Checkpoint schema for feedback elicitation
Introduce `IterationState` + `PipelineCheckpoint` in `feedback_elicitation.py`, modeled after `elicit_ambiguities.py`, with fields that match feedback steps:

**IterationState** (per iteration):
- `iteration: int`
- `model_text: str` (user_model text at iteration start)
- `model_version: int`
- `current_step: int = 0`
- `extracted_questions: list[ElicitedQuestion] | None`
- `selected_questions: list[ElicitedQuestion] | None`
- `dedup_metadata: dict[str, Any] | None`
- `user_answers: list[UserAnswerWithContext] | None`
- `updated_model_text: str | None` (set after step 5)
- `updated_model_version: int | None`

**PipelineCheckpoint** (global):
- `created_at`, `last_updated`
- `collection_id`, `rubric_description` (initial rubric)
- run params: `num_samples`, `max_questions`, `max_questions_per_run`, `max_iterations`
- `agent_run_ids: list[str] | None`
- `current_iteration: int`, `current_step: int`
- `iteration_history: list[IterationState]`
- `user_data: UserData` (latest cumulative user data)
- `user_model_text: str` and `user_model_version: int` (latest model state)
- `final_model_text: str | None`, `final_model_version: int | None`
- `convergence_reason: str | None`

This keeps the checkpoint self-contained and mirrors how `elicit_ambiguities.py` stores rubric state. Storing `user_data` + `user_model_*` at the top level avoids needing to replay QA pairs on resume.

### 3.2 Step numbering / resume-step range
Match the 5 core steps already documented in the file:
1. Extract questions
2. Deduplicate + select
3. Collect answers
4. Update UserData
5. Update UserModel

Per user feedback, **ignore decomposition analysis in checkpointing** (it’s not first‑class in the flow yet). It can continue to run after step 5, and will always re-run if you resume.

### 3.3 Resume behavior (same as elicit_ambiguities, with stricter param validation)
- Require `--resume-step` when `--resume` is used.
- `--resume-step` is `I.S` (iteration.step), with step range 1-5.
- Validate that previous steps have results before resuming.
- If resuming at an earlier iteration than the latest, truncate `iteration_history` and clear `final_model_*` + `convergence_reason`.
- Load agent runs via saved `agent_run_ids` and require at least 10 valid runs on resume.
- **Enforce run-parameter equality** on resume: if `num_samples`, `max_questions`, or `max_questions_per_run` differ from the checkpoint values, **raise a ValueError** instead of warning/overriding.
- `max_iterations` does **not** need to match; allow the provided value to override the checkpoint (same behavior as `elicit_ambiguities.py` for this parameter).
- Checkpoint file naming should match `elicit_ambiguities.py` exactly (`checkpoint_<id>_<ts>_gitignore.json`).

## 4) Implementation Plan (concrete steps)

### Step 1: Add checkpoint data models and helpers in feedback_elicitation.py
Add near the top (after `UserAnswerWithContext`), mirroring `elicit_ambiguities.py`:
- `IterationState` and `PipelineCheckpoint` BaseModels.
- `save_checkpoint(path, checkpoint)` and `load_checkpoint(path)` using `checkpoint.model_dump()` and `PipelineCheckpoint.model_validate()` with `json.dump(..., default=str)`.
- `create_checkpoint_path(collection_id)` using `checkpoint_{collection_id[:8]}_{timestamp}_gitignore.json`.
- `parse_resume_step`, `validate_resume_state`, `get_resume_state` (step range 1-5).

Include fields for `user_data` + `user_model_text` + `user_model_version` in the checkpoint. This lets `run_feedback_elicitation` restore the latest model state without recomputing.

### Step 2: Update docstring + argparse for resume options
File: `personal/mengk/rubric_elicit/feedback_elicitation.py`

- Update the top-level docstring “Usage” and “Options” to include:
  - `--resume <path>`
  - `--resume-step <I.S>`
  - A brief “Checkpointing” section like in `elicit_ambiguities.py` describing steps 1-5 and resume behavior.
- Add `--resume` (Path) and `--resume-step` (str) to argparse in `main()`.
- Update `run_feedback_elicitation` signature to accept `resume_from: Path | None` and `resume_step: str | None`.

### Step 3: Initialize or load checkpoint at start of run_feedback_elicitation
Insert logic before clients are initialized:

- If `resume_from` is provided:
  - `checkpoint = load_checkpoint(resume_from)` and `checkpoint_path = resume_from`.
  - Validate `collection_id` matches.
  - If `rubric_description` differs, warn and use checkpoint version.
  - Enforce **exact match** for `num_samples`, `max_questions`, and `max_questions_per_run`. If any differ from the checkpoint, raise a `ValueError` and stop.
  - Allow `max_iterations` to differ: if the provided value differs from the checkpoint, prefer the **provided** value and log a note (mirroring the `elicit_ambiguities.py` behavior).
  - Require `resume_step` (raise if missing).

- Else (fresh run):
  - `checkpoint_path = create_checkpoint_path(collection_id)`.
  - Initialize `user_data = UserData(initial_rubric=rubric_description)`.
  - Initialize `user_model_text = rubric_description`, `user_model_version = 1`.
  - Create `PipelineCheckpoint` with run params + user_data + model state.

### Step 4: Initialize clients + agent_runs with checkpoint support
Mirror `elicit_ambiguities`:

- If resume and `checkpoint.agent_run_ids` exists:
  - Fetch each run by ID using `dc.get_agent_run`.
  - Require at least 10 valid runs (same guard as `sample_agent_runs`).
- Else:
  - Call `sample_agent_runs`.
  - Save `checkpoint.agent_run_ids` and checkpoint immediately.

### Step 5: Determine resume state and set up model/user_data
After agent runs:

- If resume:
  - `target_iteration, target_step, existing_iter_state = get_resume_state(checkpoint, resume_step)`.
  - If resuming earlier than the last iteration, truncate `checkpoint.iteration_history` and clear final fields.
  - Load `user_data = checkpoint.user_data`.
  - Rebuild `user_model` from checkpoint fields:
    ```python
    user_model = UserModel(
        model_text=checkpoint.user_model_text,
        version=checkpoint.user_model_version,
        user_data=user_data,
    )
    ```
- Else:
  - `target_iteration, target_step, existing_iter_state = 1, 1, None`.
  - Create `user_data` and `user_model` as currently done.

Maintain `iteration_history = list(checkpoint.iteration_history)` and an `is_first_loop_iteration` flag like in `elicit_ambiguities`.

### Step 6: Add step-level checkpointing in the main loop
Adapt the existing loop to allow resuming at `target_step` and to save after each step. Mirror the `save_step_checkpoint` helper pattern from `elicit_ambiguities`.

**Helper**:
```python
def save_step_checkpoint(iter_state, step_num, iter_history, is_in_history):
    iter_state.current_step = step_num
    checkpoint.current_step = step_num
    checkpoint.current_iteration = iter_state.iteration

    if is_in_history:
        iter_history[iter_state.iteration - 1] = iter_state
    else:
        iter_history.append(iter_state)

    checkpoint.iteration_history = iter_history
    checkpoint.user_data = user_data
    checkpoint.user_model_text = user_model.model_text
    checkpoint.user_model_version = user_model.version
    checkpoint.last_updated = datetime.now(timezone.utc)
    save_checkpoint(checkpoint_path, checkpoint)
    return True
```

**Loop structure** (pseudocode):
```python
iteration = target_iteration - 1
is_first_loop_iteration = True

while iteration < max_iterations:
    iteration += 1
    checkpoint.current_iteration = iteration

    if is_first_loop_iteration and existing_iter_state and iteration == target_iteration:
        start_step = target_step
        iter_state = existing_iter_state.model_copy(deep=True)
        iter_in_history = True
    else:
        start_step = 1
        iter_state = IterationState(
            iteration=iteration,
            model_text=user_model.model_text,
            model_version=user_model.version,
        )
        iter_in_history = False
    is_first_loop_iteration = False

    # Step 1: extract
    if start_step <= 1:
        extracted_questions = await extract_questions_from_agent_runs(...)
        iter_state.extracted_questions = extracted_questions
        ... convergence if none ...
        iter_in_history = save_step_checkpoint(iter_state, 1, iteration_history, iter_in_history)
    else:
        extracted_questions = iter_state.extracted_questions or []

    # Step 2: dedup
    if start_step <= 2:
        sorted_questions = sort_questions_by_novelty(extracted_questions)
        selected_questions, dedup_metadata = await deduplicate_and_select_questions(...)
        iter_state.selected_questions = selected_questions
        iter_state.dedup_metadata = dedup_metadata
        ... convergence if none ...
        iter_in_history = save_step_checkpoint(iter_state, 2, iteration_history, iter_in_history)
    else:
        selected_questions = iter_state.selected_questions or []
        dedup_metadata = iter_state.dedup_metadata or {}

    # Step 3: collect answers
    if start_step <= 3:
        user_answers = collect_interactive_answers(selected_questions, dedup_metadata)
        iter_state.user_answers = user_answers
        ... convergence if none ...
        iter_in_history = save_step_checkpoint(iter_state, 3, iteration_history, iter_in_history)
    else:
        user_answers = iter_state.user_answers or []

    # Step 4: update UserData
    if start_step <= 4:
        for answer in user_answers: user_data.add_qa_pair(...)
        iter_in_history = save_step_checkpoint(iter_state, 4, iteration_history, iter_in_history)

    # Step 5: update UserModel
    if start_step <= 5:
        new_model_text = await update_user_model(...)
        user_model.update_model(new_model_text)
        iter_state.updated_model_text = user_model.model_text
        iter_state.updated_model_version = user_model.version
        iter_in_history = save_step_checkpoint(iter_state, 5, iteration_history, iter_in_history)

    # optional: run decomposition analysis after step 5 (not checkpointed)
    ...
```

Ensure convergence exits (no questions, user skipped) set `convergence_reason`, persist checkpoint, and break.

### Step 7: Save final checkpoint and print summary
At end (post-loop):
- If hit max iterations, set `convergence_reason = "max_iterations"`.
- Update:
  - `checkpoint.final_model_text = user_model.model_text`
  - `checkpoint.final_model_version = user_model.version`
  - `checkpoint.convergence_reason = convergence_reason`
  - `checkpoint.last_updated = now` and save.
- Keep existing final summary output.

## 5) Resolved Decisions (from user feedback)
1) Decomposition analysis is **not** part of checkpointing and will always re-run after step 5 if the user resumes.
2) On resume, enforce **exact match** for `num_samples`, `max_questions`, and `max_questions_per_run` (raise error if different).
3) Checkpoint file naming should **match** `elicit_ambiguities.py` (`checkpoint_<id>_<ts>_gitignore.json`).
4) Store `user_data` and current model state at the checkpoint top level (simplest approach).
5) `max_iterations` does **not** need to match the checkpoint; allow the provided value to override.

## 6) Open Questions / Remaining Uncertainties
- None.
