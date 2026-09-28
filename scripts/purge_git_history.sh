#!/usr/bin/env bash
# ==============================================================================
# scripts/purge_git_history.sh
#
# PURPOSE:
# Purges committed secret-bearing files (.env, historical transcripts)
# from git history using git-filter-repo before pushing to a public remote.
#
# PREREQUISITES:
# 1. Install git-filter-repo:
#    pip install git-filter-repo
#
# WARNING:
# Rewriting history changes all commit SHAs. Ensure your team is coordinated
# and you have a backup of the repository before executing.
# ==============================================================================

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

echo "=== Sandbox Siege Git History Purge ==="

if ! command -v git-filter-repo &> /dev/null; then
    echo "Error: git-filter-repo is not installed."
    echo "Install it via: pip install git-filter-repo (or python3 -m pip install git-filter-repo)"
    exit 1
fi

echo "Creating safety backup clone at ../sandbox-siege-pre-purge-backup..."
git clone --bare . ../sandbox-siege-pre-purge-backup

echo "Analyzing and scrubbing sensitive files from all branches and tags..."
# Remove .env from all history
git-filter-repo --invert-paths --path .env --force

# Remove any historical conversation transcripts from git history
git-filter-repo --invert-paths --path-glob "*transcript*.jsonl" --path-glob "*transcript*.txt" --force

echo ""
echo "=== Purge Complete ==="
echo "Git history has been rewritten to remove historical secret files."
echo "Remember to re-add your git remote if git-filter-repo unset it:"
echo "  git remote add origin https://github.com/ghassanelgendy/sandbox-siege.git"
echo "To push to your public remote:"
echo "  git push origin --force --all"
echo "  git push origin --force --tags"
