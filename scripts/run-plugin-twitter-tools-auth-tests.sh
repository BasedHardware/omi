#!/usr/bin/env bash
# Hermetic twitter tools auth tests need FastAPI TestClient (fastapi + httpx).
# Hygiene runs manifest checks on stdlib Python only; install pinned deps here
# so twitter-tools-auth-tests executes in CI instead of skipIf-vacuous green.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
python_version="$(tr -d '[:space:]' < "$repo_root/backend/.python-version")"
test_file="$repo_root/plugins/omi-twitter-chat-tools-app/test_tools_auth.py"

pinned_deps=(
  "fastapi==0.121.0"
  "httpx==0.28.1"
  "pydantic==2.13.4"
  "starlette==0.49.1"
  "requests==2.32.3"
  "python-dotenv==1.0.1"
)

run_with_uv() {
  local -a with_args=()
  for dep in "${pinned_deps[@]}"; do
    with_args+=(--with "$dep")
  done
  uv run --no-project --python "$python_version" "${with_args[@]}" -- python "$test_file"
}

run_with_python() {
  local python_bin="$1"
  if "$python_bin" -c "from fastapi.testclient import TestClient" >/dev/null 2>&1; then
    "$python_bin" "$test_file"
    return 0
  fi
  return 1
}

if command -v uv >/dev/null 2>&1; then
  run_with_uv
  exit 0
fi

if run_with_python python3; then
  exit 0
fi

# shellcheck source=dev-harness/_resolve_python.sh
if [[ -f "$repo_root/scripts/dev-harness/_resolve_python.sh" ]]; then
  source "$repo_root/scripts/dev-harness/_resolve_python.sh"
  if venv_python="$(dev_harness_canonical_python 2>/dev/null || true)" && [[ -n "$venv_python" ]]; then
    if run_with_python "$venv_python"; then
      exit 0
    fi
  fi
fi

echo "FAIL: twitter-tools-auth-tests requires uv or python with fastapi/httpx." >&2
exit 1
