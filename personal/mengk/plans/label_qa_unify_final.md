# Run-Centric QA+Label Unification Using `UserData.agent_run_feedback`

## Summary
Implement a run-centric feedback model and CLI flow where each labeling run collects:
1. Explicit answers to review-focus questions (with LLM-generated sample answers).
2. Optional final label plus explanation.
3. End-of-run review/edit before persistence.

This replaces flat `UserData.qa_pairs` and `UserData.labels` with grouped per-run feedback, and keeps `rubric_bon.py` compatible with the new schema.

## Public APIs / Interfaces / Types
1. In `user_model.py`, change `LabelingRequestFocusItem` from `text` to `question`, `citations`, and `sample_answers`.
2. In `user_model.py`, define compact run-level `QAPair` fields as: `question`, `question_citations`, `sample_answers`, `selected_sample_index`, `answer`, `status` (`answered|skipped`), `is_custom_response`, `timestamp`.
3. In `user_model.py`, add `AgentRunFeedback` with: `agent_run_id`, `title`, `review_context`, `review_context_citations`, `priority_rationale`, `priority_rationale_citations`, `qa_pairs`, `label`, `created_at`, `last_updated`.
4. In `user_model.py`, replace `UserData.qa_pairs` and `UserData.labels` with `UserData.agent_run_feedback`.
5. In `user_model.py`, remove `add_qa_pair` and `add_label`, add `upsert_run_feedback(agent_run_feedback)` that replaces by `agent_run_id`, and add helper iterators for answered QA and labeled entries used by inference/eval.
6. No legacy-schema support is implemented and no migration path is added.

## Implementation Plan
1. Refactor schema model layer in `user_model.py`.
   Set `UserData` canonical field to `agent_run_feedback`.
   Keep replacement semantics for duplicate `agent_run_id` via `upsert_run_feedback`.
   Ensure `last_updated` updates on every upsert.

2. Update labeling request prompt/parser in `elicit.py`.
   Prompt `review_focus` as object entries containing `question` and `sample_answers`.
   Parse and resolve citations for `question`.
   Parse and persist `priority_rationale` plus citations.
   Normalize `sample_answers` as string-only, trimmed, deduplicated, capped at 3, and allow fewer than 3 after normalization (no padding).

3. Migrate user-data summarization and inference in `elicit.py`.
   Flatten from `user_data.agent_run_feedback`.
   Include only QA entries where `status == "answered"` in inference summaries.
   Include labels from `agent_run_feedback.label`.
   Keep skipped QA persisted but excluded from inference content.
   Fallback to `initial_rubric` only when there are no answered QA and no labels.

4. Redesign interactive collection in `label_elicitation.py`.
   Keep run-level gate: label run / skip run / skip remaining runs.
   For each focus question: show question + citations + sample answer choices + custom + skip.
   For sample/custom selection: always allow final one-line text edit before storing.
   If no focus exists for a run, allow label-only flow with empty QA list.
   Use end-of-run review menu before persistence: save, edit focus answer(s), edit label keys, edit explanation, discard run.
   Save QA-only runs with `label=None`.
   On save where run already exists, show explicit overwrite warning and require confirmation before replacement.
   Persist through `user_data.upsert_run_feedback(...)`.

5. Update sampling and reporting in `label_elicitation.py`.
   Exclude any run already present in `agent_run_feedback` from future sampling.
   Update printed counters to include total feedback units, answered/skipped QA counts, labeled-run count, and labeled-key count.

6. Refactor holdout logic in `rubric_bon.py`.
   Split all `agent_run_feedback` units by ratio/seed, regardless of label presence.
   Build `train_user_data` from train units only.
   Derive train/test evaluation labels from labeled units inside each split.
   Ensure train inference context never includes test units.
   If either split has zero labeled runs, continue with warnings and produce `N/A` metrics for missing-side accuracy.
   Update report fields to reflect unit-level split stats and labeled-subset stats.

## Test Cases and Scenarios
1. Add unit tests for schema round-trip and replacement semantics in new/updated tests under `tests/unit/test_ai_tools`.
   Validate `agent_run_feedback` serialization/deserialization.
   Validate `upsert_run_feedback` replaces existing run ID.

2. Add unit tests for labeling-request parsing in `elicit.py`.
   Validate object-form `review_focus` parsing with citations.
   Validate `priority_rationale` parsing/citation resolution.
   Validate `sample_answers` normalization with fewer-than-3 allowed.

3. Add unit tests for user-data summarization/inference behavior in `elicit.py`.
   Answered QA is included.
   Skipped QA is excluded.
   Labels are included from nested run feedback.
   Empty answered+labels case falls back to initial rubric.

4. Add unit tests for split/isolation behavior in `rubric_bon.py`.
   All units are split, not only labeled units.
   Train and test unit IDs are disjoint in train inference context.
   Eval labels are derived only from labeled units in corresponding split.
   Zero-labeled split case produces warnings and `N/A` metrics instead of failure.

5. Add targeted non-interactive tests for CLI helper behavior in `label_elicitation.py` where feasible.
   QA-only save path.
   Overwrite warning + confirmation gate on upsert.
   Sampling exclusion includes any run with prior feedback.

## Validation Commands
1. `ruff format`
2. `ruff check`
3. `pyright docent_core/docent/ai_tools/rubric/user_model.py docent_core/docent/ai_tools/rubric/elicit.py personal/mengk/rubric_elicit/label_elicitation.py personal/mengk/rubric_elicit/rubric_bon.py`
4. `python -m pytest <new_and_updated_tests>`

## Assumptions and Defaults
1. Canonical top-level field is `UserData.agent_run_feedback`.
2. `sample_answers` is the canonical focus-default field name.
3. Compact `QAPair` is used; no separate full-trace `ReviewFocusAnswer` model.
4. Duplicate `agent_run_id` behavior is upsert-replace with explicit warning and confirmation.
5. Sampling excludes all runs that already have any saved feedback.
6. `priority_rationale` is parsed and persisted now.
7. End-of-run review/edit menu is mandatory before persistence.
8. `rubric_bon.py` split is over all feedback units; evaluation uses labeled subsets only.
9. Zero-labeled split is allowed and reported as warnings + `N/A` metrics.
10. Legacy `{qa_pairs, labels}` handling is intentionally ignored; no compatibility or migration tooling is added.
