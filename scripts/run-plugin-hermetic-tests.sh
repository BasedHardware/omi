#!/usr/bin/env bash
# Hermetic plugin suites that drive the real FastAPI app (TestClient needs
# httpx). Hygiene runs manifest checks on stdlib Python only, so install the
# pinned deps here to keep the suite from being vacuous.
set -euo pipefail

plugin_dir="${1:?usage: run-plugin-hermetic-tests.sh <plugin-dir> <test-file> [test-file...]}"
shift
if [[ $# -gt 0 ]]; then
  test_targets=("$@")
else
  test_targets=("$plugin_dir")
fi

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
python_version="$(tr -d '[:space:]' < "$repo_root/backend/.python-version")"

pinned_deps=(
  "fastapi==0.121.0"
  "httpx==0.28.1"
  "pydantic==2.13.4"
  "starlette==0.49.1"
)

if command -v uv >/dev/null 2>&1; then
  with_args=()
  for dep in "${pinned_deps[@]}"; do with_args+=(--with "$dep"); done
  uv run --no-project --python "$python_version" "${with_args[@]}" -- python -m pytest "${test_targets[@]}" -q
  exit 0
fi

# shellcheck source=dev-harness/_resolve_python.sh
source "$repo_root/scripts/dev-harness/_resolve_python.sh"
if venv_python="$(dev_harness_canonical_python 2>/dev/null || true)" && [[ -n "$venv_python" ]]; then
  if ! "$venv_python" -c "from fastapi.testclient import TestClient" 2>/dev/null; then
    echo "FAIL: $venv_python lacks fastapi/httpx; install deps or use uv." >&2
    exit 1
  fi
  "$venv_python" -m pytest "${test_targets[@]}" -q
  exit 0
fi

echo "FAIL: no hermetic Python with fastapi/httpx available." >&2
exit 1
