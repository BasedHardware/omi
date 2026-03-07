#!/usr/bin/env bash
# Configure custom merge drivers for the Nooto fork.
# Run once after cloning or in a fresh environment.

set -e

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# "ours" driver: always keep our version (fork-specific files)
git config merge.ours.driver true

# "arb" driver: keep our translations, add new upstream keys
git config merge.arb.name "ARB merge: keep ours, add new upstream keys"
git config merge.arb.driver "scripts/merge-arb.sh %A %O %B"

# Install pre-commit hook
ln -s -f ../../scripts/pre-commit .git/hooks/pre-commit

echo "Merge drivers and hooks configured."
