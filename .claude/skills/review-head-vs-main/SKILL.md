---
name: review-head-vs-main
description: Review code by diffing HEAD against main and returning issues sorted by severity/priority.
---

# Review HEAD vs main

1. Compare the branch with `main...HEAD` to understand the full change set.
   - Start with file-level scope, then inspect the diffs that matter most.

2. Review with a bug and risk mindset. Focus on correctness, regressions, data integrity, security, performance cliffs, and missing tests.

3. Report findings sorted by severity/priority.
   - Put highest-risk issues first.
   - For each issue, include: what is wrong, why it matters, and where it appears (`file:line` when possible).

4. If nothing significant is found, say that clearly and list any residual risk or test gaps.
