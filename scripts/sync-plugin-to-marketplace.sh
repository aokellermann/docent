#!/bin/bash
# Syncs the docent plugin from agent-tools to both claude-code-plugins repositories
#
# The docent plugin contains two skills:
#   - analysis: Analyzing agent behavior with Docent (SKILL.md lives at agent-tools/SKILL.md)
#   - ingestion: Structured workflow for ingesting agent run data into Docent
#
# Usage:
#   ./scripts/sync-plugin-to-marketplace.sh [--commit] [--push]
#
# Options:
#   --commit    Create a git commit in the target repo after syncing
#   --push      Push the commit to origin (implies --commit)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCENT_PLATFORM_ROOT="$(dirname "$SCRIPT_DIR")"
PLUGINS_REPO_INTERNAL="${DOCENT_PLATFORM_ROOT}/../claude-code-plugins-internal"
PLUGINS_REPO_PUBLIC="${DOCENT_PLATFORM_ROOT}/../claude-code-plugins"

SOURCE_PLUGIN="${DOCENT_PLATFORM_ROOT}/agent-tools/docent"

# The analysis skill SKILL.md lives at the root of agent-tools
ANALYSIS_SKILL_SOURCE="${DOCENT_PLATFORM_ROOT}/agent-tools/SKILL.md"

# Parse arguments
DO_COMMIT=false
DO_PUSH=false

for arg in "$@"; do
    case $arg in
        --commit)
            DO_COMMIT=true
            ;;
        --push)
            DO_COMMIT=true
            DO_PUSH=true
            ;;
    esac
done

# Validate paths
if [ ! -d "$SOURCE_PLUGIN" ]; then
    echo "Error: Source plugin not found at $SOURCE_PLUGIN"
    exit 1
fi

if [ ! -d "$PLUGINS_REPO_INTERNAL" ]; then
    echo "Error: Internal plugins repository not found at $PLUGINS_REPO_INTERNAL"
    exit 1
fi

if [ ! -d "$PLUGINS_REPO_PUBLIC" ]; then
    echo "Error: Public plugins repository not found at $PLUGINS_REPO_PUBLIC"
    exit 1
fi

if [ ! -f "$ANALYSIS_SKILL_SOURCE" ]; then
    echo "Error: Analysis SKILL.md not found at $ANALYSIS_SKILL_SOURCE"
    exit 1
fi

# Function to sync to a target repository
sync_to_repo() {
    local plugins_repo="$1"
    local target_plugin="${plugins_repo}/plugins/docent"
    local analysis_skill_target="${target_plugin}/skills/analysis/SKILL.md"

    echo "Syncing docent plugin to ${plugins_repo}..."
    echo "  Source: $SOURCE_PLUGIN"
    echo "  Target: $target_plugin"

    # Create target directory structure
    mkdir -p "$target_plugin"

    # Sync the plugin files using rsync
    # --delete ensures removed files are also removed in target
    rsync -av --delete \
        --exclude='.DS_Store' \
        "$SOURCE_PLUGIN/" "$target_plugin/"

    # Copy the analysis skill SKILL.md from agent-tools root
    echo "Copying analysis SKILL.md..."
    mkdir -p "$(dirname "$analysis_skill_target")"
    cp "$ANALYSIS_SKILL_SOURCE" "$analysis_skill_target"
}

# Sync to both repositories
sync_to_repo "$PLUGINS_REPO_INTERNAL"
sync_to_repo "$PLUGINS_REPO_PUBLIC"

echo "Sync complete!"

# Function to commit changes in a repository
commit_repo() {
    local plugins_repo="$1"
    local repo_name="$2"

    cd "$plugins_repo"

    # Check if there are changes
    if git diff --quiet && git diff --cached --quiet; then
        echo "No changes to commit in $repo_name."
    else
        git add -A

        # Get the source commit hash for reference
        SOURCE_COMMIT=$(cd "$DOCENT_PLATFORM_ROOT" && git rev-parse --short HEAD 2>/dev/null || echo "unknown")

        git commit -m "Sync docent plugin from docent-platform

Skills included:
- analysis
- ingestion

Source commit: $SOURCE_COMMIT"

        echo "Created commit in $repo_name."

        if [ "$DO_PUSH" = true ]; then
            git push origin
            echo "Pushed $repo_name to origin."
        fi
    fi
}

# Git operations
if [ "$DO_COMMIT" = true ]; then
    commit_repo "$PLUGINS_REPO_INTERNAL" "claude-code-plugins-internal"
    commit_repo "$PLUGINS_REPO_PUBLIC" "claude-code-plugins"
fi

echo "Done!"
