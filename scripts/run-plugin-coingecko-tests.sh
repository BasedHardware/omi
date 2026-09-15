#!/usr/bin/env bash
# Hermetic CoinGecko app tests drive the real FastAPI app and pydantic models
# (fastapi TestClient needs httpx). Hygiene runs manifest checks on stdlib
# Python only; install pinned deps here so the suite executes instead of
# being vacuous under stubs.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
python_version="$(tr -d '[:space:]' < "$repo_root/backend/.python-version")"
test_file="$repo_root/plugins/omi-coingecko-crypto-app/test_null_optionals.py"

pinned_deps=(
  "fastapi==0.121.0"
  "httpx==0.28.1"
  "pydantic==2.13.4"
  "starlette==0.49.1"
)

run_with_uv() {
  local -a with_args=()
  for dep in "${pinned_deps[@]}"; do
    with_args+=(--with "$dep")
  done
  uv run --no-project --python "$python_version" "${with_args[@]}" -- python "$test_file"
}

run_with_venv() {
  local python_bin="$1"
  if ! "$python_bin" -c "from fastapi.testclient import TestClient" 2>/dev/null; then
    echo "FAIL: $python_bin lacks fastapi/httpx; install deps or use uv for coingecko-null-optionals-tests." >&2
    exit 1
  fi
  "$python_bin" "$test_file"
}

if command -v uv >/dev/null 2>&1; then
  run_with_uv
  exit 0
fi

# shellcheck source=dev-harness/_resolve_python.sh
source "$repo_root/scripts/dev-harness/_resolve_python.sh"
if venv_python="$(dev_harness_canonical_python 2>/dev/null || true)" && [[ -n "$venv_python" ]]; then
  run_with_venv "$venv_python"
  exit 0
fi

echo "FAIL: coingecko-null-optionals-tests requires uv or backend/.venv with fastapi/httpx." >&2
exit 1
