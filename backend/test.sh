#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

export ENCRYPTION_SECRET="omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv"
export OPENAI_API_KEY="test-openai-key-not-real"

pytest() {
  "${PYTHON:-python3}" -m pytest "$@"
}

run_test_list() {
  local list_file="$1"
  local selected_tests=()
  local test_path
  while IFS= read -r test_path; do
    [[ -n "$test_path" ]] && selected_tests+=("$test_path")
  done < "$list_file"

  if [[ ${#selected_tests[@]} -eq 0 ]]; then
    echo "No backend unit tests selected."
    return 0
  fi

  echo "Running ${#selected_tests[@]} selected backend unit test file(s)."
  for test_path in "${selected_tests[@]}"; do
    pytest "$test_path" -v
  done
}

# CI passes an explicit list (built by scripts/select_backend_unit_tests.py).
if [[ -n "${BACKEND_UNIT_TEST_FILE_LIST:-}" ]]; then
  if [[ ! -f "$BACKEND_UNIT_TEST_FILE_LIST" ]]; then
    echo "BACKEND_UNIT_TEST_FILE_LIST does not exist: $BACKEND_UNIT_TEST_FILE_LIST" >&2
    exit 1
  fi
  run_test_list "$BACKEND_UNIT_TEST_FILE_LIST"
  exit 0
fi

# Local runs discover tests with the same selector CI uses, so the local and
# CI test sets can never drift apart. New test files under tests/unit/,
# tests/services/, or tests/routers/ are picked up automatically.
LOCAL_TEST_LIST="$(mktemp)"
trap 'rm -f "$LOCAL_TEST_LIST"' EXIT
"${PYTHON:-python3}" scripts/select_backend_unit_tests.py --all --output "$LOCAL_TEST_LIST"
run_test_list "$LOCAL_TEST_LIST"

# Fair-use integration tests (require Redis; skip gracefully if unavailable)
if redis-cli ping >/dev/null 2>&1; then
  pytest tests/integration/test_fair_use_live.py -v
  pytest tests/integration/test_fair_use_api.py -v
else
  echo "SKIP: fair-use integration tests (Redis not available)"
fi
