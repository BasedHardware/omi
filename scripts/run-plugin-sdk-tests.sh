#!/usr/bin/env bash
# The omi-plugin-sdk suite drives the real pydantic models, so hygiene's
# stdlib-only Python cannot execute it. Install the SDK's single pinned
# dependency here and put src/ on the path (the README's `pip install -e`
# layout) so the suite runs instead of being skipped.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
python_version="$(tr -d '[:space:]' < "$repo_root/backend/.python-version")"
sdk_src="$repo_root/plugins/omi-plugin-sdk/src"
test_files=(
  "$repo_root/plugins/omi-plugin-sdk/tests/test_models.py"
)

pinned_deps=(
  "pydantic==2.13.4"
  "pytest==8.4.1"
)

export PYTHONPATH="$sdk_src${PYTHONPATH:+:$PYTHONPATH}"

run_with_uv() {
  local -a with_args=()
  for dep in "${pinned_deps[@]}"; do
    with_args+=(--with "$dep")
  done
  uv run --no-project --python "$python_version" "${with_args[@]}" -- python -m pytest "${test_files[@]}" -q
}

run_with_venv() {
  local python_bin="$1"
  if ! "$python_bin" -c "import pydantic, pytest" 2>/dev/null; then
    echo "FAIL: $python_bin lacks pydantic/pytest; install deps or use uv for plugin-sdk-model-tests." >&2
    exit 1
  fi
  "$python_bin" -m pytest "${test_files[@]}" -q
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

echo "FAIL: plugin-sdk-model-tests requires uv or backend/.venv with pydantic/pytest." >&2
exit 1
