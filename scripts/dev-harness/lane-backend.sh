#!/usr/bin/env bash
# Opt-in wheel install for mobile-session start and the pre-push typecheck gate.
#
# Not lock-hash identical. `make setup` / `make setup-backend` remain the
# contributor entrypoint and run `uv pip sync` of pylock.macos.toml.
#
# This command uses `uv pip install -r backend/requirements.txt` (index wheels).
# The pylock lists hashed sdist+wheel for av/llvmlite/scipy/pyarrow; a lock
# sync can fall through to those sdists (~20 min). Sufficient for uvicorn /
# pyright / yaml / dotenv / google.auth — not for lock-hash identity.
set -euo pipefail

STARTED=$SECONDS
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

VENV_PY="$ROOT/backend/.venv/bin/python"
REQUIREMENTS="$ROOT/backend/requirements.txt"
# mobile-session start (uvicorn + google.*) and pre-push typecheck (pyright),
# plus the cheap-gate imports (yaml, dotenv).
PROBE='import dotenv, google.auth, pyright, uvicorn, yaml'

probe_ok() {
  local python_bin="$1"
  [[ -x "$python_bin" ]] || return 1
  "$python_bin" -c "$PROBE" >/dev/null 2>&1
}

echo "lane-backend: worktree $ROOT"
echo "lane-backend: route=uv pip install -r backend/requirements.txt (not uv pip sync pylock)"
echo "lane-backend: not lock-hash identical; use make setup for the locked environment."
echo "lane-backend: pylock lists hashed sdist+wheel for av/llvmlite/scipy/pyarrow; sync can fall through to those sdists (~20 min). requirements.txt takes index wheels."

if ! command -v uv >/dev/null 2>&1; then
  echo "FAIL: uv is required. Install: https://docs.astral.sh/uv/" >&2
  exit 1
fi
if [[ ! -f "$REQUIREMENTS" ]]; then
  echo "FAIL: $REQUIREMENTS is missing." >&2
  exit 1
fi

if [[ -x "$VENV_PY" ]] && [[ "$("$VENV_PY" --version 2>&1 || true)" == *3.11.* ]]; then
  echo "lane-backend: existing Python 3.11 at backend/.venv"
else
  uv python install 3.11
  uv venv --allow-existing --python 3.11 backend/.venv
  if [[ ! -x "$VENV_PY" ]]; then
    echo "FAIL: $VENV_PY was not created." >&2
    exit 1
  fi
fi

if probe_ok "$VENV_PY"; then
  elapsed=$((SECONDS - STARTED))
  echo "lane-backend: probe ok (uvicorn, pyright, yaml, dotenv, google.auth) — already complete, skipped pip"
  echo "lane-backend: done in ${elapsed}s"
  exit 0
fi

echo "lane-backend: incomplete venv — installing backend/requirements.txt"
uv pip install --python "$VENV_PY" -r "$REQUIREMENTS"
if ! probe_ok "$VENV_PY"; then
  echo "FAIL: $VENV_PY still cannot import uvicorn, pyright, yaml, dotenv, google.auth after install." >&2
  exit 1
fi

elapsed=$((SECONDS - STARTED))
echo "lane-backend: installed from backend/requirements.txt"
echo "lane-backend: probe ok (uvicorn, pyright, yaml, dotenv, google.auth)"
echo "lane-backend: done in ${elapsed}s"
