# Run-Centric Review-Focus QA + Labeling Overhaul

## Summary
Implement a run-centric feedback model and CLI flow where each labeling run collects:
1. Explicit answers to review-focus questions (with LLM-generated sample answers).
2. Optional final label plus explanation.
3. End-of-run review/edit before persistence.

This replaces flat `UserData.qa_pairs` and `UserData.labels` with grouped per-run feedback, and keeps `rubric_bon.py` compatible with the new schema.

## Interface and Data Model Changes

### Files
- `docent_core/docent/ai_tools/rubric/user_model.py`
- `docent_core/docent/ai_tools/rubric/elicit.py`

### Changes
1. Replace `LabelingRequestFocusItem.text` with:
   - `question: str`
   - `citations: list[InlineCitation]`
   - `sample_answers: list[str]` (target 3)

2. Replace flat user data structure with run-grouped structure:
   - Add `AgentRunFeedback` model with:
     - `agent_run_id`
     - `title`
     - `review_context`, `review_context_citations`
     - `priority_rationale`, `priority_rationale_citations`
     - `qa_pairs: list[QAPair]`
     - `label: LabeledRun | None`
     - `created_at`, `last_updated`
   - Update `QAPair` to include:
     - `question`, `question_citations`
     - `sample_answers`
     - `selected_sample_index: int | None`
     - `answer: str | None`
     - `status: Literal["answered", "skipped"]`
     - `is_custom_response`
     - `timestamp`
   - Update `UserData` to store:
     - `run_feedback: list[AgentRunFeedback]`
     - helper methods:
       - `upsert_run_feedback` (replace by `agent_run_id`)
       - iterators/helpers for answered QA and labels for inference

3. No backward compatibility for old JSON shape:
   - remove top-level `qa_pairs` and `labels` as persisted fields
   - update loaders/validators to expect run-grouped schema

## LLM Labeling Request Generation Updates

### File
- `docent_core/docent/ai_tools/rubric/elicit.py`

### Changes
1. Update `create_labeling_request_prompt` to request `review_focus` entries as objects:
   - each entry includes `question` and exactly 3 `sample_answers`
   - questions remain rubric-anchored and citation-tagged

2. Update parser in `generate_labeling_requests`:
   - parse object-form `review_focus`
   - resolve citations on `question`
   - normalize `sample_answers` (string-only, dedupe, cap at 3)

3. Update user-data summarization/inference helpers:
   - iterate through `run_feedback`
   - include only `QAPair.status == "answered"` in inference prompts
   - include labels from `run_feedback.label`
   - keep label evidence formatting behavior

## CLI Flow Redesign

### File
- `personal/mengk/rubric_elicit/label_elicitation.py`

### Changes
1. Replace per-run label-only collection with per-run feedback draft:
   - stage A: review-focus QA first
   - stage B: label key selection
   - stage C: label explanation
   - stage D: end-of-run review/edit menu

2. Review-focus question interaction per item:
   - show question plus citations
   - options:
     - sample answer 1/2/3
     - `None of the above, write my own`
     - `Skip this question`
   - after selecting sample/custom, prompt for editable final answer (single-line prompt)

3. Final run review/edit menu:
   - `Save run feedback`
   - `Edit specific review-focus answer`
   - `Edit label key values`
   - `Edit label explanation`
   - `Discard this run`
   - This guarantees post-hoc editing before persistence.

4. Persistence behavior:
   - save QA-only runs (`label=None`) when user skips labeling
   - store skipped questions with explicit `status="skipped"`
   - `upsert` run feedback by `agent_run_id` (replace existing)

5. Sampling exclusion policy:
   - exclude any run already present in `UserData.run_feedback` (not just labeled runs)

6. Update printed metrics:
   - number of run feedback entries saved
   - answered vs skipped focus questions
   - number of runs with labels and total labeled keys

## `rubric_bon.py` Compatibility Migration

### File
- `personal/mengk/rubric_elicit/rubric_bon.py`

### Changes
1. Load new `UserData.run_feedback` schema and top-level keys.
2. Derive labeled examples from `run_feedback` entries where `label is not None`.
3. Train/test split over labeled run-feedback entries.
4. Build train `UserData` by including:
   - all QA-only run-feedback entries
   - train-labeled run-feedback entries
   - excluding test-labeled run-feedback entirely (including their QA) to avoid leakage
5. Update all label-count/reporting fields to use derived labeled-entry counts.

## Validation and Testing
1. Add/adjust unit tests in `tests` for:
   - labeling request parse with object-form `review_focus` plus sample answers
   - run-grouped `UserData` summarization includes answered QA and excludes skipped QA
   - `upsert_run_feedback` replacement behavior
   - inference fallback when there is no answered QA and no labels

2. Manual CLI acceptance scenarios for `label_elicitation.py`:
   - sample answer selection plus edit path
   - custom answer path
   - skipped question persistence
   - QA-only save (no label)
   - end-of-run edit menu modifies previously entered QA/label before save
   - skip run and skip future runs still function

3. Static checks after implementation:
   - `ruff format`
   - `pyright`

## Assumptions and Defaults Locked
1. Include `rubric_bon.py` migration.
2. Generate 3 sample answers per review-focus question.
3. Persist skipped questions with explicit skipped status.
4. Save run feedback even when label is absent.
5. Exclude any run with existing feedback from future sampling.
6. Exclude skipped QA from user-model inference prompts.
7. Use inline single-line answer editing prompts.
8. Use end-of-run section-based edit menu.
9. In `rubric_bon`, exclude QA from test-labeled runs to prevent leakage.
10. On duplicate `agent_run_id`, replace existing run feedback entry.
