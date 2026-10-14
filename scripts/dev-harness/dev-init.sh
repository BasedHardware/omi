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
if [ ! -x "backend/.venv/bin/python" ] && [ ! -x "backend/.venv/Scripts/python.exe" ]; then
  BOOTSTRAP_PY="$(dev_harness_python)"
  "$BOOTSTRAP_PY" -m venv backend/.venv
  echo "Created backend/.venv (with $BOOTSTRAP_PY)"
fi

PYTHON_BIN="$(dev_harness_python)"
case "$PYTHON_BIN" in
  *backend/.venv/*) ;;
  *)
    echo "dev-init: resolved interpreter '$PYTHON_BIN' is not backend/.venv; refusing to install requirements outside the venv." >&2
    echo "The venv is missing or below the 3.10 floor. Run: make lane-bootstrap (Python 3.11 venv)," >&2
    echo "or install Python >= 3.10 and re-run dev-init." >&2
    exit 1
    ;;
esac
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
