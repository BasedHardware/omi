#!/usr/bin/env bash
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REQUIREMENTS="$BACKEND_DIR/openapi-requirements.txt"
VENV_DIR="${OPENAPI_RUNNER_VENV:-$BACKEND_DIR/.openapi-venv}"
PYTHON_VERSION="$(cat "$BACKEND_DIR/.python-version")"
PYTHON_MINOR="${PYTHON_VERSION%.*}"
PYTHON_BIN="${OPENAPI_RUNNER_PYTHON:-python$PYTHON_MINOR}"

if [ ! -f "$REQUIREMENTS" ]; then
  echo "FAIL: missing OpenAPI runner requirements at $REQUIREMENTS" >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "FAIL: uv is required for the OpenAPI runner. Install uv or run with CI's setup-uv step." >&2
  exit 1
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN=python3
fi

if [ -x "$VENV_DIR/bin/python" ]; then
  VENV_PYTHON_VERSION="$("$VENV_DIR/bin/python" -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')"
  if [ "$VENV_PYTHON_VERSION" != "$PYTHON_MINOR" ]; then
    rm -rf "$VENV_DIR"
  fi
fi

if [ ! -x "$VENV_DIR/bin/python" ]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

uv pip sync --python "$VENV_DIR/bin/python" "$REQUIREMENTS"

"$VENV_DIR/bin/python" - <<'PY'
import tiktoken

tiktoken.encoding_for_model('gpt-4')
PY

cd "$BACKEND_DIR"
exec "$VENV_DIR/bin/python" "$@"
