#!/usr/bin/env bash
# Runs Swift XCTest suites in isolated processes, with opt-in parallelism.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT_PATH="$SCRIPT_DIR/$(basename "$0")"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SKIP_RATCHET="$SCRIPT_DIR/swift-test-skip-ratchet.py"
MAIN_ACTOR_XCTEST_HOOK_GUARD="$SCRIPT_DIR/check-main-actor-xctest-hooks.py"
TESTS_ROOT="${OMI_SWIFT_TEST_DISCOVERY_ROOT:-$MACOS_DIR/Desktop/Tests}"
PACKAGE_PATH="${OMI_SWIFT_TEST_PACKAGE_PATH:-Desktop}"
# Each suite runs in an independent SwiftPM process because of process-global
# test state. CI has proven four-way execution safe; make that the local
# default too, while preserving an explicit one-worker escape hatch for a
# diagnosis (`OMI_SWIFT_TEST_SUITE_WORKERS=1`).
WORKERS="${OMI_SWIFT_TEST_SUITE_WORKERS:-${SWIFT_TEST_SUITE_WORKERS:-4}}"
PREBUILD="${OMI_SWIFT_TEST_PREBUILD:-1}"
SUITE_TIMEOUT_SECONDS="${OMI_SWIFT_TEST_SUITE_TIMEOUT_SECONDS:-120}"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

terminate_process_tree() {
  local pid="$1"
  local signal="$2"
  local children child
  children="$(pgrep -P "$pid" 2>/dev/null || true)"
  for child in $children; do
    terminate_process_tree "$child" "$signal"
  done
  if kill -0 "$pid" 2>/dev/null; then
    kill "-$signal" "$pid" 2>/dev/null || true
  fi
}

run_suite() {
  local log_dir="$1"
  local suite="$2"
  local log_path="$log_dir/$suite.log"
  local status_path="$log_dir/$suite.status"
  local timeout_path="$log_dir/$suite.timeout"
  local -a skip_args=()

  while IFS= read -r skip_arg; do
    skip_args+=("$skip_arg")
  done < <("$SKIP_RATCHET" --args-for-suite "$suite")
  local -a build_args=()
  if [ "$PREBUILD" = "1" ]; then
    build_args+=("--skip-build")
  fi
  local -a command=(xcrun swift test --package-path "$PACKAGE_PATH" "${build_args[@]}" --filter "${suite}/")
  if [ "${#skip_args[@]}" -gt 0 ]; then
    command+=("${skip_args[@]}")
  fi
  set +e
  "${command[@]}" >"$log_path" 2>&1 &
  local command_pid=$!
  (
    sleep "$SUITE_TIMEOUT_SECONDS"
    if kill -0 "$command_pid" 2>/dev/null; then
      touch "$timeout_path"
      terminate_process_tree "$command_pid" TERM
      sleep 5
      terminate_process_tree "$command_pid" KILL
    fi
  ) &
  local watchdog_pid=$!
  wait "$command_pid"
  local status=$?
  kill "$watchdog_pid" 2>/dev/null || true
  wait "$watchdog_pid" 2>/dev/null || true
  if [ -f "$timeout_path" ]; then
    echo "suite timed out after ${SUITE_TIMEOUT_SECONDS}s" >>"$log_path"
    status=124
  fi
  set -e
  echo "$status" >"$status_path"
  exit "$status"
}

if [ "${1:-}" = "__run_suite" ]; then
  run_suite "$2" "$3"
fi

[[ "$WORKERS" =~ ^[0-9]+$ ]] || fail "worker count must be a positive integer, got '$WORKERS'"
if [ "$WORKERS" -lt 1 ]; then
  fail "worker count must be at least 1"
fi
if [ "$PREBUILD" != "0" ] && [ "$PREBUILD" != "1" ]; then
  fail "OMI_SWIFT_TEST_PREBUILD must be 0 or 1, got '$PREBUILD'"
fi
[[ "$SUITE_TIMEOUT_SECONDS" =~ ^[0-9]+$ ]] \
  || fail "OMI_SWIFT_TEST_SUITE_TIMEOUT_SECONDS must be a positive integer, got '$SUITE_TIMEOUT_SECONDS'"
if [ "$SUITE_TIMEOUT_SECONDS" -lt 1 ]; then
  fail "OMI_SWIFT_TEST_SUITE_TIMEOUT_SECONDS must be at least 1"
fi

# Static guardrails are part of the authoritative Swift component suite, not a
# separate best-effort lint. Run their fixture tests first so a broken checker
# cannot turn a green scan into false confidence. Skip when the hermetic
# launcher fixture overrides discovery — that path only validates runner
# parallelism/skip wiring, and the real suite job already runs the ratchet.
if [ -z "${OMI_SWIFT_TEST_DISCOVERY_ROOT:-}" ]; then
  python3 "$SCRIPT_DIR/tests/test_check_desktop_test_quality.py"
  python3 "$SCRIPT_DIR/check_desktop_test_quality.py"
  python3 "$MAIN_ACTOR_XCTEST_HOOK_GUARD"
fi

# Discover suites recursively so tests in subfolders of Desktop/Tests are not
# silently skipped (SwiftPM compiles the whole Tests target; this must match).
declare -a suites=()
while IFS= read -r suite; do
  suites+=("$suite")
done < <(find "$TESTS_ROOT" -type f -name '*.swift' -print0 \
  | xargs -0 grep -hE '^[[:space:]]*(@[A-Za-z0-9_]+[[:space:]]+)*(public |internal |private |fileprivate |open )?(final )?(class|extension) [A-Za-z0-9_]+:.*XCTestCase' \
  | sed -E 's/^[[:space:]]*(@[A-Za-z0-9_]+[[:space:]]+)*(public |internal |private |fileprivate |open )?(final )?(class|extension) ([A-Za-z0-9_]+):.*/\5/' \
  | sort -u)

"$SKIP_RATCHET" --check --tests-root "$TESTS_ROOT"

cd "$MACOS_DIR"
suite_log_dir="$(mktemp -d)"
trap 'rm -rf "$suite_log_dir"' EXIT
failed_suites=""
suite_count="${#suites[@]}"

if [ "$PREBUILD" = "1" ] && [ "$suite_count" -gt 0 ]; then
  echo "Prebuilding Swift test bundle before parallel suite execution..."
  xcrun swift build --package-path "$PACKAGE_PATH" --build-tests
fi

if [ "$suite_count" -gt 0 ]; then
  printf '%s\0' "${suites[@]}" \
    | xargs -0 -n1 -P "$WORKERS" "$SCRIPT_PATH" __run_suite "$suite_log_dir" || true
fi

for suite in "${suites[@]}"; do
  status_path="$suite_log_dir/$suite.status"
  if [ ! -f "$status_path" ]; then
    failed_suites="$failed_suites $suite"
    echo "--- FAILED: $suite ---"
    echo "suite did not produce a status file"
    continue
  fi
  if [ "$(cat "$status_path")" != "0" ]; then
    failed_suites="$failed_suites $suite"
    echo "--- FAILED: $suite ---"
    cat "$suite_log_dir/$suite.log"
  fi
done

echo "Ran $suite_count Swift suites in isolation with $WORKERS worker(s)."

if [ -n "$failed_suites" ]; then
  echo "FAILED Swift suites:$failed_suites"
  exit 1
fi
