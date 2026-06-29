#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

export ENCRYPTION_SECRET="omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv"

PYTHON_BIN="${PYTHON:-python3}"
if ! "$PYTHON_BIN" -m pytest --version >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

read_test_file_list() {
  local test_file_list="$1"
  if [[ -n "$test_file_list" ]]; then
    if [[ ! -f "$test_file_list" ]]; then
      echo "ERROR: BACKEND_UNIT_TEST_FILE_LIST does not exist: $test_file_list" >&2
      exit 1
    fi
    python scripts/select_backend_unit_tests.py --from-test-list "$test_file_list"
  else
    python scripts/select_backend_unit_tests.py --all
  fi
}

pytest_args=(-v)
if [[ "${BACKEND_PYTEST_XDIST:-auto}" != "0" ]]; then
  if "$PYTHON_BIN" -c "import xdist" >/dev/null 2>&1; then
    pytest_args+=("-n" "${BACKEND_PYTEST_WORKERS:-auto}" "--dist=loadfile")
  else
    echo "pytest-xdist not installed; running backend unit tests without parallel workers."
  fi
fi

requires_process_isolation() {
  local test_path="$1"
  grep -Eq 'sys[.]modules|importlib[.]reload|del sys[.]modules' "$test_path"
}

run_pytest_group() {
  local label="$1"
  shift
  if [[ $# -eq 0 ]]; then
    return 0
  fi

  echo
  echo "----------------------------------------"
  echo "Running $label ($# files)"
  echo "----------------------------------------"

  if ! "$PYTHON_BIN" -m pytest "$@" "${pytest_args[@]}"; then
    failed_tests+=("$label")
  fi
}

run_isolated_pytest() {
  local test_path="$1"

  echo
  echo "----------------------------------------"
  echo "Running isolated $test_path"
  echo "----------------------------------------"

  if ! "$PYTHON_BIN" -m pytest "$test_path" -v; then
    failed_tests+=("$test_path")
  fi
}

unit_tests=()
while IFS= read -r test_path; do
  unit_tests+=("$test_path")
done < <(read_test_file_list "${BACKEND_UNIT_TEST_FILE_LIST:-}")

bulk_tests=()
isolated_tests=()
for test_path in "${unit_tests[@]}"; do
  if requires_process_isolation "$test_path"; then
    isolated_tests+=("$test_path")
  else
    bulk_tests+=("$test_path")
  fi
done

failed_tests=()

echo
echo "----------------------------------------"
if [[ ${#unit_tests[@]} -eq 0 ]]; then
  echo "No backend unit tests selected."
else
  echo "Running ${#unit_tests[@]} backend unit test files"
  echo "Bulk files: ${#bulk_tests[@]}"
  echo "Isolated files: ${#isolated_tests[@]}"
fi
echo "----------------------------------------"

if [[ ${#unit_tests[@]} -gt 0 ]]; then
  run_pytest_group "bulk backend unit tests" "${bulk_tests[@]}"
  for test_path in "${isolated_tests[@]}"; do
    run_isolated_pytest "$test_path"
  done
fi

# Optional fair-use integration tests require Redis and are intentionally outside
# the deterministic unit signal.
if [[ "${RUN_BACKEND_INTEGRATION_TESTS:-0}" == "1" ]]; then
  if command -v redis-cli >/dev/null 2>&1 && redis-cli ping >/dev/null 2>&1; then
    if ! "$PYTHON_BIN" -m pytest tests/integration/test_fair_use_live.py tests/integration/test_fair_use_api.py -v; then
      failed_tests+=("fair-use integration tests")
    fi
  else
    echo "SKIP: fair-use integration tests (Redis not available)"
  fi
else
  echo "SKIP: fair-use integration tests (set RUN_BACKEND_INTEGRATION_TESTS=1 to enable)"
fi

echo
echo "----------------------------------------"
if [[ ${#failed_tests[@]} -eq 0 ]]; then
  echo "All backend tests passed."
  exit 0
fi

echo "Backend test failures (${#failed_tests[@]}):"
printf '  - %s\n' "${failed_tests[@]}"
exit 1
