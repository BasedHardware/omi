#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=_resolve_python.sh
source "$(dirname "$0")/_resolve_python.sh"
cd "$(dirname "$0")/../.."

echo "Omi local dev harness — one-time setup"

secrets_file="backend/.env.local-dev"
template="backend/.env.local-dev.template"
if [ ! -f "$secrets_file" ]; then
  cp "$template" "$secrets_file"
  echo "Created $secrets_file from template"
else
  echo "Keeping existing $secrets_file (not overwritten)"
fi

# Bootstrap the venv with the resolver's pick BEFORE it exists: with no venv,
# dev_harness_python returns a floor-qualified interpreter when one exists
# (python3.12/Homebrew prefix), so the created venv satisfies the 3.10 floor.
# Creation keys on the venv's absence (a floor-qualified fallback on a fresh
# checkout must not skip it — Codex P1), and the install below runs only
# through the venv, never a global interpreter (Codex/Oracle follow-up: a
# 3.9-only host must not have its requirements installed globally either).
# Prefer the repo-pinned 3.11 backend runtime when it is discoverable — the
# backend pylock declares `>=3.11,<3.12` and mobile_doctor rejects a non-3.11
# backend venv — falling back to the pre-push floor pick only when no 3.11
# is discoverable without installing anything (Codex P1).
VENV_PREEXISTED=0
if [ -x "backend/.venv/bin/python" ] || [ -x "backend/.venv/Scripts/python.exe" ]; then
  VENV_PREEXISTED=1
fi
if [ "$VENV_PREEXISTED" -eq 0 ]; then
  BOOTSTRAP_PY=""
  if BOOTSTRAP_PY="$(dev_harness_backend_pinned_python)"; then
    echo "Using the repo-pinned backend runtime: $BOOTSTRAP_PY"
  else
    BOOTSTRAP_PY="$(dev_harness_python)"
    echo "dev-init: no pinned Python 3.11 discoverable; bootstrapping with the floor pick $BOOTSTRAP_PY" >&2
    echo "dev-init: the backend pylock is >=3.11,<3.12 — run 'make lane-backend' to upgrade this venv to 3.11." >&2
  fi
  # A bare-3.9 bootstrap would create a venv every later resolver call
  # rejects; stop here with the documented guidance instead (Codex P2).
  if ! dev_harness_python_floor_ok "$BOOTSTRAP_PY"; then
    dev_harness_python_floor_advisory
    exit 1
  fi
  "$BOOTSTRAP_PY" -m venv backend/.venv
  echo "Created backend/.venv (with $BOOTSTRAP_PY)"
fi

# A pre-existing venv that the resolver rejects (below the 3.10 floor) must
# not receive this install: the resolver ignores it, so dev-init would report
# success while dev-harness/pre-push refuses the environment it just
# provisioned (Codex P1). The resolver emits the actionable guidance itself.
if [ "$VENV_PREEXISTED" -eq 1 ]; then
  # stdout (the resolved path) is discarded; the resolver's stderr names the
  # exact reason (below-floor or missing cheap-gate imports).
  if ! dev_harness_canonical_python >/dev/null; then
    echo "dev-init: the existing backend/.venv is not usable by the dev harness (below the 3.10 floor or missing cheap-gate imports); refusing to install requirements into it." >&2
    echo "Run: make lane-bootstrap (Python 3.11 venv), or recreate it: rm -rf backend/.venv && dev-init." >&2
    exit 1
  fi
fi

# Select the executable for the layout that exists (native Windows venvs use
# Scripts/python.exe; POSIX use bin/python — Codex P1).
if [ -x "$PWD/backend/.venv/bin/python" ]; then
  PYTHON_BIN="$PWD/backend/.venv/bin/python"
elif [ -x "$PWD/backend/.venv/Scripts/python.exe" ]; then
  PYTHON_BIN="$PWD/backend/.venv/Scripts/python.exe"
else
  echo "dev-init: backend/.venv exists but has no interpreter; recreate it (python3 -m venv backend/.venv or make lane-bootstrap)." >&2
  exit 1
fi
# Bind the install to THIS repo's venv python directly: re-running the resolver
# here would reject a freshly created venv (it cannot import dotenv/yaml before
# this install — Codex P1) and fall back to a global interpreter. The
# sys.prefix membership check below keeps the binding honest: the venv python
# must report this venv (its realpath) as its prefix, so a symlinked venv
# python pointing at a foreign interpreter is still refused.
CANONICAL_PREFIX="$(cd "$PWD/backend/.venv" 2>/dev/null && pwd -P)" || CANONICAL_PREFIX=""
if [ -z "$CANONICAL_PREFIX" ]; then
  echo "dev-init: backend/.venv is missing; refusing to install requirements outside the venv." >&2
  echo "Run: make lane-bootstrap (Python 3.11 venv), or install Python >= 3.10 and re-run dev-init." >&2
  exit 1
fi
INTERPRETER_PREFIX="$("$PYTHON_BIN" -c 'import sys; print(sys.prefix)' 2>/dev/null)" || INTERPRETER_PREFIX=""
INTERPRETER_PREFIX_PHYS=""
if [ -n "$INTERPRETER_PREFIX" ] && [ -d "$INTERPRETER_PREFIX" ]; then
  INTERPRETER_PREFIX_PHYS="$(cd "$INTERPRETER_PREFIX" && pwd -P)" || INTERPRETER_PREFIX_PHYS=""
fi
if [ "$INTERPRETER_PREFIX_PHYS" != "$CANONICAL_PREFIX" ]; then
  echo "dev-init: '$PYTHON_BIN' does not belong to this repo's backend/.venv (sys.prefix '$INTERPRETER_PREFIX'); refusing to install requirements outside the venv." >&2
  echo "The venv is missing or below the 3.10 floor. Run: make lane-bootstrap (Python 3.11 venv)," >&2
  echo "or install Python >= 3.10 and re-run dev-init." >&2
  exit 1
fi
if ! "$PYTHON_BIN" -m pip --version >/dev/null; then
  echo "${PYTHON_BIN%/bin/python} is incomplete; recreate it with: python3 -m venv backend/.venv" >&2
  exit 1
fi

"$PYTHON_BIN" -m pip install -q -r backend/requirements.txt
echo "Backend Python dependencies installed"

# scripts/install-git-hooks.sh owns hook installation. A linked worktree's
# `.git` is a file holding a gitdir pointer, so a literal `.git/hooks` path does
# not exist there; the installer resolves the shared hook directory with
# `git rev-parse --git-path hooks` and installs dispatchers rather than symlinks
# into a directory every worktree shares.
bash scripts/install-git-hooks.sh

echo ""
echo "Next: add your four API keys to backend/.env.local-dev, then run:"
echo "  make dev-up        # start the harness for mobile/iOS testing"
echo "  make dev-desktop   # start the harness and the desktop app"
