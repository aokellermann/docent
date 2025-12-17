#!/bin/bash
set -e

# Cleanup old backup branches from before the current month
# Backup branches are created by deploy.sh with format: {branch}-backup-{YYYYMMDDHHMMSS}

# Calculate current month prefix (YYYYMM)
CURRENT_MONTH_PREFIX=$(date +%Y%m)

echo "Looking for backup branches older than: $(date +%Y-%m)"
echo ""

# Fetch latest remote refs
git fetch origin --prune

# Find all backup branches from before the current month
BRANCHES_TO_DELETE=()
while IFS= read -r branch; do
  # Extract the timestamp portion (last 14 characters before any trailing whitespace)
  # Branch format: origin/{name}-backup-{YYYYMMDDHHMMSS}
  if [[ "$branch" =~ -backup-([0-9]{14})$ ]]; then
    TIMESTAMP="${BASH_REMATCH[1]}"
    BRANCH_YYYYMM="${TIMESTAMP:0:6}"

    # Delete if branch is from before current month
    if [ "$BRANCH_YYYYMM" -lt "$CURRENT_MONTH_PREFIX" ]; then
      # Remove "origin/" prefix for deletion
      BRANCH_NAME="${branch#origin/}"
      BRANCHES_TO_DELETE+=("$BRANCH_NAME")
    fi
  fi
done < <(git branch -r | grep -- '-backup-' | tr -d ' ')

if [ ${#BRANCHES_TO_DELETE[@]} -eq 0 ]; then
  echo "No backup branches found from before $(date +%Y-%m)"
  exit 0
fi

echo "Found ${#BRANCHES_TO_DELETE[@]} backup branch(es) to delete:"
for branch in "${BRANCHES_TO_DELETE[@]}"; do
  echo "  - $branch"
done
echo ""

# Confirm deletion
read -p "Delete ${#BRANCHES_TO_DELETE[@]} branches from remote? (y/N): " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
  echo "Operation cancelled."
  exit 0
fi

# Delete branches
for branch in "${BRANCHES_TO_DELETE[@]}"; do
  echo "Deleting: $branch"
  git push origin --delete "$branch"
done

echo ""
echo "Done! Deleted ${#BRANCHES_TO_DELETE[@]} backup branch(es)."
