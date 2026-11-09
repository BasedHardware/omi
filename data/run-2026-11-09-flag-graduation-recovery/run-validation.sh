#!/usr/bin/env bash
# Local-only recovery validation. Invoke through the workspace's omi-heavy.
set -uo pipefail
TASK_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$TASK_ROOT"
unset GOOGLE_APPLICATION_CREDENTIALS
for name in ${!CLOUDSDK_@}; do
  unset "$name"
done
export PATH="$TASK_ROOT/backend/.venv/bin:$PATH"
TASK_LOG_DIR="${1:?pass a disposable output directory on Ephemeral}"
mkdir -p "$TASK_LOG_DIR"
TASK_FAILED=0
run_check() {
  local label="$1"
  shift
  "$@" > "$TASK_LOG_DIR/$label.log" 2>&1
  local result=$?
  printf '%s\t%s\n' "$label" "$result" >> "$TASK_LOG_DIR/results.tsv"
  tail -25 "$TASK_LOG_DIR/$label.log"
  if [[ "$result" -ne 0 ]]; then TASK_FAILED=1; fi
}
: > "$TASK_LOG_DIR/results.tsv"
run_check registry backend/.venv/bin/python scripts/check_feature_flag_registry.py
run_check registry-tests backend/.venv/bin/python -m pytest -q scripts/test_check_feature_flag_registry.py
if [[ "${2:-registry-only}" == all ]]; then
  # Match the file-isolated backend contract, including every touched module.
  git diff --name-only cb58353ace9f^ HEAD > "$TASK_LOG_DIR/changed.txt"
  backend/.venv/bin/python backend/scripts/select_backend_unit_tests.py \
    --changed-files "$TASK_LOG_DIR/changed.txt" \
    --output "$TASK_LOG_DIR/tests.txt" \
    --reason-output "$TASK_LOG_DIR/selection-reason.txt"
  if [[ $? -ne 0 ]]; then exit 1; fi
  export BACKEND_PYTEST_WORKERS=4
  export BACKEND_UNIT_TEST_FILE_LIST="$TASK_LOG_DIR/tests.txt"
  run_check backend-tests bash backend/test.sh
fi
exit "$TASK_FAILED"
