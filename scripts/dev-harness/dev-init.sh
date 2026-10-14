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

# Bootstrap the venv with the repo-pinned 3.11 backend runtime BEFORE it
# exists. The backend pylock declares `>=3.11,<3.12` and mobile_doctor
# rejects a non-3.11 backend venv, so dev-init refuses rather than provision
# a backend-incompatible environment (Codex P1 + Oracle review). Discovery:
# PATH python3.11, then uv-managed 3.11; provisioning context may install the
# pinned runtime with `uv python install 3.11` — exactly what
# `make lane-backend` does. Pre-push keeps its own broader 3.10 floor; this
# is the backend requirements install, which serves the backend, not the gate.
VENV_PREEXISTED=0
if [ -x "backend/.venv/bin/python" ] || [ -x "backend/.venv/Scripts/python.exe" ]; then
  VENV_PREEXISTED=1
fi
if [ "$VENV_PREEXISTED" -eq 0 ]; then
  if ! BOOTSTRAP_PY="$(dev_harness_backend_pinned_python)"; then
    if command -v uv >/dev/null 2>&1 \
      && uv python install 3.11 >/dev/null 2>&1 \
      && BOOTSTRAP_PY="$(dev_harness_backend_pinned_python)"; then
      echo "Using uv-provisioned repo-pinned backend runtime: $BOOTSTRAP_PY"
    else
      echo "dev-init: no Python 3.11 could be provisioned for backend/.venv." >&2
      echo "The backend pylock requires >=3.11,<3.12 (mobile_doctor rejects any other version)." >&2
      echo "Fix: install Python 3.11 (e.g. 'brew install python@3.11' or 'uv python install 3.11'), then re-run dev-init." >&2
      exit 1
    fi
  else
    echo "Using the repo-pinned backend runtime: $BOOTSTRAP_PY"
  fi
  "$BOOTSTRAP_PY" -m venv backend/.venv
  echo "Created backend/.venv (with $BOOTSTRAP_PY)"
fi

# An existing venv must hold the pinned backend runtime before it receives
# the backend requirements install (Codex P1 + Oracle review): 3.11 — with
# complete or interrupted/incomplete packages — is the only acceptable state
# and dev-init completes the install; any other version (3.9/3.10 below the
# floor, or 3.12+ above the pin) is backend-incompatible and refused with the
# recreate guidance — mobile_doctor and the pylock reject it anyway, so
# installing into it would only fake success.
if [ "$VENV_PREEXISTED" -eq 1 ]; then
  VENV_PY_BIN="$PWD/backend/.venv/bin/python"
  [ -x "$VENV_PY_BIN" ] || VENV_PY_BIN="$PWD/backend/.venv/Scripts/python.exe"
  if ! dev_harness_venv_python_is_pinned_311 "$VENV_PY_BIN"; then
    echo "dev-init: the existing backend/.venv is not the pinned Python 3.11 runtime the backend requires; refusing to install requirements into it." >&2
    echo "Recover with: rm -rf backend/.venv && make dev-init (re-runs the pinned" >&2
    echo "3.11 discovery), or: make lane-bootstrap (requires uv)." >&2
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
  echo "dev-init: backend/.venv exists but has no interpreter; recreate it with the pinned runtime:" >&2
  echo "  python3.11 -m venv backend/.venv   (or: make lane-bootstrap)" >&2
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
  echo "Run: make lane-bootstrap (Python 3.11 venv), or install Python 3.11 and re-run dev-init." >&2
  exit 1
fi
INTERPRETER_PREFIX="$("$PYTHON_BIN" -c 'import sys; print(sys.prefix)' 2>/dev/null)" || INTERPRETER_PREFIX=""
# Native Windows Python reports a drive path (C:\...); Git Bash's filesystem
# operators need the POSIX form, matching the cygpath conversion used for uv
# results in _resolve_python.sh (Codex P1).
if command -v cygpath >/dev/null 2>&1; then
  INTERPRETER_PREFIX="$(cygpath -u "$INTERPRETER_PREFIX" 2>/dev/null || printf '%s' "$INTERPRETER_PREFIX")"
fi
INTERPRETER_PREFIX_PHYS=""
if [ -n "$INTERPRETER_PREFIX" ] && [ -d "$INTERPRETER_PREFIX" ]; then
  INTERPRETER_PREFIX_PHYS="$(cd "$INTERPRETER_PREFIX" && pwd -P)" || INTERPRETER_PREFIX_PHYS=""
fi
if [ "$INTERPRETER_PREFIX_PHYS" != "$CANONICAL_PREFIX" ]; then
  echo "dev-init: '$PYTHON_BIN' does not belong to this repo's backend/.venv (sys.prefix '$INTERPRETER_PREFIX'); refusing to install requirements outside the venv." >&2
  echo "The venv is missing or points at another checkout. Recreate it pinned:" >&2
  echo "  rm -rf backend/.venv && python3.11 -m venv backend/.venv, or run: make lane-bootstrap." >&2
  exit 1
fi
if ! "$PYTHON_BIN" -m pip --version >/dev/null; then
  echo "$PYTHON_BIN is incomplete; recreate the venv pinned: rm -rf backend/.venv && python3.11 -m venv backend/.venv" >&2
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
