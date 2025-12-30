#!/bin/bash
set -e

# Navigate to project root directory
ROOT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." &> /dev/null && pwd )"
cd "$ROOT_DIR"

# Create a new worktree and branch from within current git directory.

if [[ -z "$1" ]]; then
  echo "Usage: gwa.sh [branch name]" >&2
  exit 1
fi

branch="$1"
base="$(basename "$PWD")"
# Replace '/' with '--' in branch name to avoid nested folder structure
safe_branch="${branch//\//-}"
path="../${base}--${safe_branch}"

git worktree add -b "$branch" "$path" >&2

# Print the path so caller can cd to it: cd $(gwa.sh branch)
echo "$path"
