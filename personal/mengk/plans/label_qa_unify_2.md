# Run-Centric Focus-QA + Label Elicitation Redesign (with Hard Train/Test Isolation)

## Summary
Restructure elicitation data around per-agent-run feedback objects, add explicit focus-question answering with LLM-generated default answers before labeling, and enforce strict `rubric_bon.py` train/test separation by `agent_run_id` so no test QA or labels leak into train.

## Public API / Type Changes
1. In [user_model.py](/Users/mengk/Code/docent--kmeng01-jl/docent_core/docent/ai_tools/rubric/user_model.py), change `LabelingRequestFocusItem` from `text` to:
   `question`, `citations`, `suggested_answers`.
2. Add `ReviewFocusAnswer` with full trace:
   `focus_index`, `question`, `question_citations`, `suggested_answers`, `selected_mode` (`suggested|none_of_the_above|skipped`), `selected_suggested_answer_index`, `selected_suggested_answer`, `initial_answer`, `final_answer`, `is_edited`, `timestamp`.
3. Add `AgentRunFeedback`:
   `agent_run_id`, `title`, `review_context`, `review_context_citations`, `priority_rationale`, `priority_rationale_citations`, `review_focus`, `qa_pairs`, `label`, `created_at`, `last_updated`.
4. Replace `UserData.qa_pairs` and `UserData.labels` with `UserData.agent_run_feedback`.
5. Keep `LabeledRun` payload for label content/metadata, but run-level context lives in `AgentRunFeedback`.

## Implementation Plan

1. Refactor [user_model.py](/Users/mengk/Code/docent--kmeng01-jl/docent_core/docent/ai_tools/rubric/user_model.py).
   Remove backward compatibility expectations for legacy JSON.
   Add `add_run_feedback(...)` and remove old `add_qa_pair` / `add_label`.

2. Extend labeling request generation in [elicit.py](/Users/mengk/Code/docent--kmeng01-jl/docent_core/docent/ai_tools/rubric/elicit.py).
   Prompt the LLM to return `review_focus` as objects: `question` + 3 `suggested_answers`.
   Parse and normalize to exactly 3 non-empty suggestions.
   Parse/store `priority_rationale` with citations.
   Keep robust fallback when focus is malformed/empty.

3. Update user-data summarization/inference in [elicit.py](/Users/mengk/Code/docent--kmeng01-jl/docent_core/docent/ai_tools/rubric/elicit.py).
   Flatten from `agent_run_feedback` entries.
   Include answered QA and labels.
   Persist skipped QA but exclude skipped QA from inference prompt content.
   Update empty-data checks and logging counters.

4. Rework interactive flow in [label_elicitation.py](/Users/mengk/Code/docent--kmeng01-jl/personal/mengk/rubric_elicit/label_elicitation.py).
   Per run: context display -> focus Q&A -> label keys -> explanation -> per-run edit/confirm loop.
   For each focus: show 3 suggestions + `None of the above (write my own)` + `Skip` + `Restart run`.
   Always allow editing selected/default text before finalizing each answer.
   Persist QA-only runs when label is skipped.
   If no focus exists, use label-only fallback for that run.
   Keep run-level skip controls (`skip run`, `skip remaining runs`).

5. Update persistence and sampling in [label_elicitation.py](/Users/mengk/Code/docent--kmeng01-jl/personal/mengk/rubric_elicit/label_elicitation.py).
   Load/save new `UserData` shape.
   Exclude already-labeled runs by checking `agent_run_feedback` entries with non-null `label`.
   Report counts: total run-feedback entries, answered QA, skipped QA, labeled entries.

6. Update `rubric_bon.py` with hard split by `agent_run_id`.
   In [rubric_bon.py](/Users/mengk/Code/docent--kmeng01-jl/personal/mengk/rubric_elicit/rubric_bon.py), derive split units from labeled `agent_run_id`s.
   Assign each run ID to exactly one split.
   Build `train_user_data` using only run-feedback entries whose `agent_run_id` is in `train_run_ids`.
   Build test evaluation labels only from `test_run_ids`.
   Exclude all run-feedback (QA + label) for `test_run_ids` from train inference input.
   This guarantees no QA or label leakage from test into train.

## Tests and Scenarios
1. Unit test: `LabelingRequest` parser handles focus objects and 3-answer normalization.
2. Unit test: summarization excludes skipped QA but keeps answered QA and labels.
3. Unit test: `UserData` new schema round-trip with QA-only and labeled entries.
4. Unit test: `rubric_bon` split enforces disjoint `train_run_ids` and `test_run_ids`, and train prompt data contains no entries from `test_run_ids`.
5. Manual CLI test: answer/edit/skip focus questions, skip label for one run (QA-only save), confirm per-run edit loop works.

## Validation Commands
1. `pyright docent_core/docent/ai_tools/rubric/user_model.py docent_core/docent/ai_tools/rubric/elicit.py personal/mengk/rubric_elicit/label_elicitation.py personal/mengk/rubric_elicit/rubric_bon.py`
2. `ruff format`
3. `ruff check`
4. `python -m pytest <updated unit tests>`

## Assumptions and Defaults
1. No backward compatibility with old `UserData` JSON.
2. Suggested answers per focus: exactly 3.
3. Skipped QA is persisted for audit but excluded from inference prompt.
4. QA-only runs are persisted when label is absent.
5. Repeated `agent_run_id` entries are append-only in `UserData`.
6. `rubric_bon` uses hard split by `agent_run_id` to prevent any QA/label leakage.
