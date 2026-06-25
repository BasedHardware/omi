#!/usr/bin/env bash
# Refresh the backend uv pylocks from the human-maintained requirements files.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_VERSION="$(tr -d '[:space:]' < .python-version)"
IFS=. read -r PYTHON_MAJOR PYTHON_MINOR _ <<< "$PYTHON_VERSION"
PYLOCK_REQUIRES_PYTHON=">=${PYTHON_MAJOR}.${PYTHON_MINOR},<${PYTHON_MAJOR}.$((PYTHON_MINOR + 1))"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install it from https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi

compile_lock() {
  local platform="$1"
  local output_file="$2"
  shift 2

  local compile_cmd=(uv pip compile "$@")
  if [[ "${PYLOCK_UPGRADE:-0}" == "1" ]]; then
    compile_cmd+=(--upgrade)
  fi

  compile_cmd+=(
    --format pylock.toml \
    --python "$PYTHON_VERSION" \
    --python-platform "$platform" \
    --output-file "$output_file" \
    --custom-compile-command 'backend/scripts/update-python-lock.sh'
  )
  "${compile_cmd[@]}"

  sed -i.bak "s/^requires-python = .*/requires-python = \"$PYLOCK_REQUIRES_PYTHON\"/" "$output_file"
  rm -f "$output_file.bak"
}

uv python install "$PYTHON_VERSION"
compile_lock x86_64-unknown-linux-gnu pylock.toml requirements.txt testing/e2e/requirements.txt
compile_lock aarch64-apple-darwin pylock.macos.toml requirements.txt testing/e2e/requirements.txt
compile_lock x86_64-apple-darwin pylock.macos-x86_64.toml requirements.txt testing/e2e/requirements.txt
compile_lock x86_64-pc-windows-msvc pylock.windows.toml requirements.txt testing/e2e/requirements.txt
compile_lock x86_64-unknown-linux-gnu pylock.runtime.toml requirements.txt
compile_lock x86_64-unknown-linux-gnu pusher/pylock.toml pusher/requirements.txt
compile_lock x86_64-unknown-linux-gnu agent-proxy/pylock.toml agent-proxy/requirements.txt
