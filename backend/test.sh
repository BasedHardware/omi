#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

export ENCRYPTION_SECRET="omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv"
export OPENAI_API_KEY="test-openai-key-not-real"
PYTHON_BIN="${PYTHON:-python3}"

pytest() {
  "$PYTHON_BIN" -m pytest "$@"
}

run_test_files() {
  if [[ $# -eq 0 ]]; then
    return 0
  fi

  if [[ -n "${BACKEND_PYTEST_XDIST:-}" && "${BACKEND_PYTEST_XDIST:-}" != "0" ]]; then
    "$PYTHON_BIN" - "$@" <<'PY'
from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import os
import subprocess
import sys


def _worker_count(test_count: int) -> int:
    raw = os.environ.get('BACKEND_PYTEST_WORKERS') or os.environ.get('BACKEND_PYTEST_XDIST') or 'auto'
    if raw == 'auto':
        return max(1, min(test_count, os.cpu_count() or 1))
    try:
        return max(1, min(test_count, int(raw)))
    except ValueError:
        return 1


def _run_test(test_path: str) -> tuple[str, int, str]:
    proc = subprocess.run(
        [sys.executable, '-m', 'pytest', test_path, '-v'],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return test_path, proc.returncode, proc.stdout


tests = sys.argv[1:]
workers = _worker_count(len(tests))
print(f'Running {len(tests)} backend unit test file(s) with {workers} isolated worker process(es).', flush=True)

failed = False
with ThreadPoolExecutor(max_workers=workers) as executor:
    pending = {executor.submit(_run_test, test_path) for test_path in tests}
    while pending:
        done, pending = wait(pending, return_when=FIRST_COMPLETED)
        for future in done:
            test_path, returncode, output = future.result()
            print(f'::group::{test_path}', flush=True)
            print(output, end='' if output.endswith('\n') else '\n')
            print('::endgroup::', flush=True)
            if returncode:
                failed = True

if failed:
    raise SystemExit(1)
PY
    return
  fi

  for test_path in "$@"; do
    pytest "$test_path" -v
  done
}

if [[ -n "${BACKEND_UNIT_TEST_FILE_LIST:-}" ]]; then
  if [[ ! -f "$BACKEND_UNIT_TEST_FILE_LIST" ]]; then
    echo "BACKEND_UNIT_TEST_FILE_LIST does not exist: $BACKEND_UNIT_TEST_FILE_LIST" >&2
    exit 1
  fi

  selected_tests=()
  while IFS= read -r test_path; do
    [[ -n "$test_path" ]] && selected_tests+=("$test_path")
  done < "$BACKEND_UNIT_TEST_FILE_LIST"

  if [[ ${#selected_tests[@]} -eq 0 ]]; then
    echo "No backend unit tests selected."
    exit 0
  fi

  echo "Running ${#selected_tests[@]} selected backend unit test file(s)."
  run_test_files "${selected_tests[@]}"
  exit 0
fi

selected_tests=()
selected_tests_file="$(mktemp "${TMPDIR:-/tmp}/backend-unit-tests.XXXXXX")"
trap 'rm -f "$selected_tests_file"' EXIT
"$PYTHON_BIN" scripts/select_backend_unit_tests.py --all > "$selected_tests_file"
while IFS= read -r test_path; do
  [[ -n "$test_path" ]] && selected_tests+=("$test_path")
done < "$selected_tests_file"
echo "Running ${#selected_tests[@]} backend unit test file(s)."
run_test_files "${selected_tests[@]}"
