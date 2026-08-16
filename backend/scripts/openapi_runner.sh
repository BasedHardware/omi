#!/usr/bin/env bash
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REQUIREMENTS="$BACKEND_DIR/openapi-requirements.txt"
DEFAULT_VENV_DIR="$BACKEND_DIR/.openapi-venv"
VENV_DIR="${OPENAPI_RUNNER_VENV:-$DEFAULT_VENV_DIR}"
PYTHON_VERSION="$(cat "$BACKEND_DIR/.python-version")"
PYTHON_MINOR="${PYTHON_VERSION%.*}"
PYTHON_BIN="${OPENAPI_RUNNER_PYTHON:-python$PYTHON_MINOR}"

find_venv_python() {
  local candidate
  for candidate in "$VENV_DIR/bin/python" "$VENV_DIR/Scripts/python.exe"; do
    if [ -x "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

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

VENV_PYTHON="$(find_venv_python || true)"
if [ -n "$VENV_PYTHON" ]; then
  VENV_PYTHON_VERSION="$("$VENV_PYTHON" -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')"
  if [ "$VENV_PYTHON_VERSION" != "$PYTHON_MINOR" ]; then
    if [ "$VENV_DIR" != "$DEFAULT_VENV_DIR" ]; then
      echo "FAIL: custom OpenAPI runner venv at $VENV_DIR uses Python $VENV_PYTHON_VERSION; expected $PYTHON_MINOR. Remove or replace it explicitly." >&2
      exit 1
    fi
    rm -rf "$VENV_DIR"
    VENV_PYTHON=""
  fi
fi

if [ -z "$VENV_PYTHON" ]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
  VENV_PYTHON="$(find_venv_python || true)"
fi

if [ -z "$VENV_PYTHON" ]; then
  echo "FAIL: OpenAPI runner venv has no supported Python executable under $VENV_DIR" >&2
  exit 1
fi

uv pip sync --python "$VENV_PYTHON" "$REQUIREMENTS"

"$VENV_PYTHON" - <<'PY'
import tiktoken

tiktoken.encoding_for_model('gpt-4')
PY

cd "$BACKEND_DIR"
exec "$VENV_PYTHON" "$@"
