#!/usr/bin/env bash
# Refresh the backend uv pylocks from the human-maintained requirements files.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_VERSION="$(tr -d '[:space:]' < .python-version)"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install it from https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi

compile_lock() {
  local platform="$1"
  local output_file="$2"
  shift 2

  if [[ "${PYLOCK_UPGRADE:-0}" == "1" ]]; then
    uv pip compile \
      "$@" \
      --upgrade \
      --format pylock.toml \
      --python "$PYTHON_VERSION" \
      --python-platform "$platform" \
      --output-file "$output_file" \
      --custom-compile-command 'backend/scripts/update-python-lock.sh'
  else
    uv pip compile \
      "$@" \
      --format pylock.toml \
      --python "$PYTHON_VERSION" \
      --python-platform "$platform" \
      --output-file "$output_file" \
      --custom-compile-command 'backend/scripts/update-python-lock.sh'
  fi
}

uv python install "$PYTHON_VERSION"
compile_lock x86_64-unknown-linux-gnu pylock.toml requirements.txt testing/e2e/requirements.txt
compile_lock aarch64-apple-darwin pylock.macos.toml requirements.txt testing/e2e/requirements.txt
compile_lock x86_64-apple-darwin pylock.macos-x86_64.toml requirements.txt testing/e2e/requirements.txt
compile_lock x86_64-pc-windows-msvc pylock.windows.toml requirements.txt testing/e2e/requirements.txt
compile_lock x86_64-unknown-linux-gnu pylock.runtime.toml requirements.txt
compile_lock x86_64-unknown-linux-gnu pusher/pylock.toml pusher/requirements.txt
