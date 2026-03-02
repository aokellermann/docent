---
name: create-pr
description: Creates a new PR from the current branch, analyzing changes against the base branch and drafting a title and description.
---

# Create PR

When this skill is invoked, create a new pull request from the current branch.

## Workflow

1. **Check current state**:
   - Run `git branch --show-current` to get the current branch name
   - If on `main`, stop and tell the user they need to be on a feature branch
   - Run `git status` to check for uncommitted changes — warn the user if there are any

2. **Determine base branch**: Default to `main`. If the user specifies a different base, use that instead.

3. **Push the branch**: Run `git push -u origin <branch>` to ensure the remote is up to date.

4. **Analyze changes**:
   - Run `git diff main...HEAD` to see all changes
   - Run `git log main...HEAD --oneline` to see commit history
   - Understand the full scope of what changed

5. **Create the PR** using `gh pr create`:
   - Draft a concise title (under 70 characters) summarizing the changes
   - Draft a description using this format:

   ```
   ## Summary
   <1-3 bullet points explaining what changed and why>

   ## Test plan
   <Bulleted checklist of how to verify the changes>
   ```

   - Use a HEREDOC for the body to preserve formatting:

   ```bash
   gh pr create --title "the pr title" --body "$(cat <<'EOF'
   ## Summary
   ...

   ## Test plan
   ...
   EOF
   )"
   ```

6. **Report**: Show the new PR URL to the user.
