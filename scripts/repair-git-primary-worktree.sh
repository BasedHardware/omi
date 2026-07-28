#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${1:-$ROOT}"

# Primary checkout: repo-root `.git` is a directory. A mistaken `core.bare=true` makes
# Git treat this path as a bare repo: `git status` and `show-toplevel` fail here,
# and `git worktree list` labels the main path "(bare)" even though the tree exists.
if [ ! -d "$TARGET/.git" ] || [ -f "$TARGET/.git" ]; then
  exit 0
fi

if [ "$(git -C "$TARGET" config --get core.bare 2>/dev/null || echo false)" != "true" ]; then
  exit 0
fi

echo "Repairing mistaken core.bare=true on primary checkout at $TARGET" >&2
git -C "$TARGET" config core.bare false
