#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
python_version="3.11"
test_dir="$repo_root/plugins/omi-crossref-app"

pinned_deps=(
  "fastapi==0.104.1"
  "httpx==0.27.0"
  "pydantic==2.5.2"
  "pytest==8.3.5"
)

if command -v uv >/dev/null 2>&1; then
  with_args=()
  for dep in "${pinned_deps[@]}"; do
    with_args+=(--with "$dep")
  done
  exec uv run --no-project --python "$python_version" "${with_args[@]}" -- \
    python -m pytest "$test_dir" -q
fi

# shellcheck source=dev-harness/_resolve_python.sh
source "$repo_root/scripts/dev-harness/_resolve_python.sh"
python_bin="$(dev_harness_canonical_python 2>/dev/null || true)"
if [[ -n "$python_bin" ]] && "$python_bin" -c "import fastapi, httpx, pydantic, pytest" 2>/dev/null; then
  exec "$python_bin" -m pytest "$test_dir" -q
fi

echo "FAIL: Crossref plugin tests require uv or a configured Python environment." >&2
exit 1
