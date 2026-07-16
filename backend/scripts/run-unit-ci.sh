#!/usr/bin/env bash
# Run the backend unit-test contract shared by pre-push and GitHub Actions.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$BACKEND_DIR"

usage() {
  echo "usage: $0 --all | --changed-files <repo-relative-path-list>" >&2
  exit 2
}

mode="${1:-}"
case "$mode" in
  --all)
    [ "$#" -eq 1 ] || usage
    ;;
  --changed-files)
    [ "$#" -eq 2 ] && [ -f "$2" ] || usage
    ;;
  *)
    usage
    ;;
esac

PYTHON_BIN="${PYTHON:-}"
if [ -z "$PYTHON_BIN" ]; then
  if [ -x .venv/bin/python ]; then
    PYTHON_BIN=.venv/bin/python
  else
    PYTHON_BIN=python3
  fi
fi

selected_tests="$(mktemp "${TMPDIR:-/tmp}/omi-backend-unit-tests.XXXXXX")"
selection_reason="$(mktemp "${TMPDIR:-/tmp}/omi-backend-unit-tests-reason.XXXXXX")"
trap 'rm -f "$selected_tests" "$selection_reason"' EXIT

selector_args=(--output "$selected_tests" --reason-output "$selection_reason")
if [ "$mode" = "--all" ]; then
  selector_args+=(--all)
else
  selector_args+=(--changed-files "$2")
fi
"$PYTHON_BIN" scripts/select_backend_unit_tests.py "${selector_args[@]}"

selected_count="$(wc -l < "$selected_tests" | tr -d ' ')"
reason="$(cat "$selection_reason")"

PYTHON="$PYTHON_BIN" bash test-preflight.sh
PYTHON="$PYTHON_BIN" bash scripts/typecheck.sh

if [ "$selected_count" -eq 0 ]; then
  echo "No backend unit tests selected: $reason"
  exit 0
fi

echo "Selected $selected_count backend unit test file(s): $reason"
BACKEND_UNIT_TEST_FILE_LIST="$selected_tests" \
BACKEND_FAST_UNIT_WARN_SECONDS="0.1" \
BACKEND_FAST_UNIT_FAIL_SECONDS="1.0" \
BACKEND_PYTEST_FILE_ISOLATION="1" \
BACKEND_PYTEST_MARK_EXPR="not integration and not slow" \
BACKEND_PYTEST_XDIST="auto" \
BACKEND_PYTEST_WORKERS="auto" \
PYTHON="$PYTHON_BIN" \
bash test.sh
