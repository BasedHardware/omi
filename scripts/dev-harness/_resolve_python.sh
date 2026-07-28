#!/usr/bin/env bash

# Print the interpreter for local dev-harness commands. PYTHON is an explicit
# caller choice; otherwise prefer the canonical venv while retaining support
# for existing checkouts that use the legacy backend/venv location.
dev_harness_python() {
  if [ -n "${PYTHON:-}" ]; then
    printf '%s\n' "$PYTHON"
    return
  fi

  local repo_root candidate
  repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
  for candidate in "$repo_root/backend/.venv/bin/python" "$repo_root/backend/venv/bin/python"; do
    if [ -x "$candidate" ]; then
      printf '%s\n' "$candidate"
      return
    fi
  done

  printf '%s\n' "python3"
}
