---
name: update-pr
description: Updates a PR description to reflect the current state of changes between HEAD and the base branch.
---

# Update PR Description

When this skill is invoked, update the PR description for the current branch to accurately reflect the changes between HEAD and the base branch. Preserve any relevant manual notes from the existing description.

## Workflow

1. **Get PR info**: Run `gh pr view --json number,baseRefName,body,url` to get:
   - The PR number
   - The base branch name
   - The existing PR body (to preserve manual notes)
   - The PR URL (to show the user at the end)

2. **Analyze changes**:
   - Run `git diff <base>...HEAD` to see all changes
   - Run `git log <base>...HEAD --oneline` to see commit history
   - Understand the full scope of what changed

3. **Draft updated description**:
   - Focus on the "why" behind changes, not just listing files
   - Preserve any manual notes or context from the existing description that are still relevant

4. **Update the PR body** using `gh api` (see critical note below)

## Critical: Updating PR Body

**`gh pr edit` does NOT work for updating the PR body.** You must use the GitHub API directly:

```bash
gh api repos/{owner}/{repo}/pulls/{number} -X PATCH -f body="$(cat <<'EOF'
## Summary
...

## Test plan
...
EOF
)"
```

Get the owner/repo from `gh repo view --json owner,name`.
