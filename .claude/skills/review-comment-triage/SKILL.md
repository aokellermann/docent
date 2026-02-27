---
name: review-comment-triage
description: Evaluate and handle PR/code review comments by first checking whether the comment is correct, then either implementing a fix or explaining why no change should be made. Use when asked to address, resolve, or respond to review feedback.
---

# Review Comment Triage

Treat every review comment as a hypothesis, not a fact.

## Workflow

1. Validate the comment before changing code.
   - Restate the reviewer claim in precise technical terms.
   - Inspect the relevant code, tests, and surrounding context.
   - Classify the claim as `valid`, `partially valid`, or `invalid`.

2. Act based on the validation result.
   - If `valid`: implement the smallest correct fix at the root cause, then run the relevant checks/tests.
   - If `partially valid`: fix the valid portion and explicitly document the part that should not be changed.
   - If `invalid`: do not make code changes for the comment; prepare a concise explanation with technical evidence.

3. Report clearly.
   - For accepted comments, summarize what changed and how it was validated.
   - For rejected comments, explain why the current behavior is correct (or why tradeoffs favor the current implementation).
