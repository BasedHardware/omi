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

  uv pip compile \
    requirements.txt \
    testing/e2e/requirements.txt \
    --format pylock.toml \
    --python "$PYTHON_VERSION" \
    --python-platform "$platform" \
    --output-file "$output_file" \
    --custom-compile-command 'backend/scripts/update-python-lock.sh'
}

uv python install "$PYTHON_VERSION"
compile_lock x86_64-unknown-linux-gnu pylock.toml
compile_lock aarch64-apple-darwin pylock.macos.toml
compile_lock x86_64-apple-darwin pylock.macos-x86_64.toml
compile_lock x86_64-pc-windows-msvc pylock.windows.toml
