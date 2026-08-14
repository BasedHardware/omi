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
# These suites exercise the production-standard UserDefaults auth domain. On
# hosted runners CoreFoundation can still route that domain through the shared
# cfprefsd service even when workers have distinct CFFIXED_USER_HOME values.
# Keep the small auth cluster sequential and give each suite a fresh runtime;
# the remaining hundreds of suites retain worker-level parallelism.
# Membership is also derived from the source below, so a new adopter of the
# owner-authority fixture cannot silently rejoin the parallel pool.
SERIAL_SUITES="${OMI_SWIFT_TEST_SERIAL_SUITES:-APIClientAuthRetryTests AuthRefreshResilienceTests AuthSessionAttemptFenceTests AuthTokenStorageTests ChatToolExecutorCreateMemoryTests FirebaseAuthAvailabilityTests KernelJournalOwnerBoundAuthTests RuntimeOwnerIdentityTests}"
PREBUILD="${OMI_SWIFT_TEST_PREBUILD:-1}"
# The per-suite budget must clear the slowest legitimate suite, not the median
# one: MemoryAtlasPerformanceHarnessTests runs 19 tests whose XCTest `measure`
# blocks take ~245s in isolation, so a 120s local default reported it FAILED on
# a clean main while CI (300s, see .github/workflows/desktop-swift-ci.yml) was
# green. Keep this in sync with that workflow — the check below proves it.
SUITE_TIMEOUT_SECONDS="${OMI_SWIFT_TEST_SUITE_TIMEOUT_SECONDS:-300}"
# A suite killed by a signal writes nothing but SwiftPM's one-line "Exited with
# unexpected signal code N" into its log — no frames. The system crash reporter
# holds the backtrace, and on a hosted runner it is discarded with the machine,
# so a crasher that only reproduces on CI is undebuggable from the log alone
# (#11573). Print the reports this run produced next to the failing suites.
CRASH_REPORT_DIR="${OMI_SWIFT_TEST_CRASH_REPORT_DIR:-$HOME/Library/Logs/DiagnosticReports}"
CRASH_REPORT_LIMIT="${OMI_SWIFT_TEST_CRASH_REPORT_LIMIT:-6}"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

dump_crash_reports() {
  local marker="$1"
  if [ ! -d "$CRASH_REPORT_DIR" ]; then
    echo "No crash reports: $CRASH_REPORT_DIR does not exist."
    return
  fi
  local reports
  reports="$(find "$CRASH_REPORT_DIR" -maxdepth 1 -type f -name '*.ips' -newer "$marker" 2>/dev/null \
    | sort | head -n "$CRASH_REPORT_LIMIT")"
  if [ -z "$reports" ]; then
    echo "No crash reports newer than this run in $CRASH_REPORT_DIR."
    return
  fi
  local report
  while IFS= read -r report; do
    echo "--- CRASH REPORT: $report ---"
    cat "$report"
    echo
  done <<<"$reports"
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
  local build_path="$3"
  local runtime_path="$4"
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
  local -a command=(
    xcrun swift test --package-path "$PACKAGE_PATH" --scratch-path "$build_path" "${build_args[@]}" --filter "${suite}/"
  )
  if [ "${#skip_args[@]}" -gt 0 ]; then
    command+=("${skip_args[@]}")
  fi
  set +e
  # XCTest launches every filtered suite in the same `xctest` host bundle, so
  # its standard UserDefaults domain and user-domain paths would otherwise be
  # shared even when the SwiftPM scratch directories are distinct. Keep every
  # worker's preferences, Application Support, and temporary files separate.
  # CFFIXED_USER_HOME makes CoreFoundation preferences and Foundation's
  # user-domain directories (Application Support, Caches) follow the worker
  # home without changing the shell HOME used by package dependencies.
  env CFFIXED_USER_HOME="$runtime_path/home" TMPDIR="$runtime_path/tmp" \
    "${command[@]}" >"$log_path" 2>&1 &
  local command_pid=$!
  (
    # Parallel workers share one SwiftPM `.build` lock, so `swift test` can block
    # on "Another instance of SwiftPM is already running ... waiting" before it
    # executes anything. That queue time must not count against the per-suite run
    # budget, or a merely-queued suite gets killed as if it hung. Spend the run
    # budget only while the suite is NOT parked on the build lock (its log's last
    # line is that wait message); a separate, generous cap still fails a suite
    # that can never acquire the lock (e.g. a wedged holder).
    local lock_wait_cap="${OMI_SWIFT_TEST_LOCK_WAIT_CAP_SECONDS:-1200}"
    local remaining="$SUITE_TIMEOUT_SECONDS"
    local lock_waited=0
    while kill -0 "$command_pid" 2>/dev/null; do
      sleep 1
      if tail -n 1 "$log_path" 2>/dev/null | grep -q "Another instance of SwiftPM is already running"; then
        lock_waited=$((lock_waited + 1))
        [ "$lock_waited" -lt "$lock_wait_cap" ] && continue
      else
        lock_waited=0
        remaining=$((remaining - 1))
        [ "$remaining" -gt 0 ] && continue
      fi
      touch "$timeout_path"
      terminate_process_tree "$command_pid" TERM
      sleep 5
      terminate_process_tree "$command_pid" KILL
      exit 0
    done
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

run_worker() {
  local log_dir="$1"
  local suite_list="$2"
  local build_path="$3"
  local runtime_path="$4"
  local suite

  # Suites retain their process isolation, but a worker owns one cloned SwiftPM
  # scratch directory. This avoids the shared `.build` lock that made CI's
  # original parallel runner report queued suites as false timeouts. The
  # worker also owns its process-global Foundation state.
  while IFS= read -r suite; do
    "$SCRIPT_PATH" __run_suite "$log_dir" "$suite" "$build_path" "$runtime_path" || true
  done <"$suite_list"
}

if [ "${1:-}" = "__run_suite" ]; then
  run_suite "$2" "$3" "$4" "$5"
fi

if [ "${1:-}" = "__run_worker" ]; then
  run_worker "$2" "$3" "$4" "$5"
  exit 0
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
suite_class_pattern='^[[:space:]]*(@[A-Za-z0-9_]+[[:space:]]+)*(public |internal |private |fileprivate |open )?(final )?(class|extension) [A-Za-z0-9_]+:.*XCTestCase'
suite_class_name='s/^[[:space:]]*(@[A-Za-z0-9_]+[[:space:]]+)*(public |internal |private |fileprivate |open )?(final )?(class|extension) ([A-Za-z0-9_]+):.*/\5/'

declare -a suites=()
while IFS= read -r suite; do
  suites+=("$suite")
done < <(find "$TESTS_ROOT" -type f -name '*.swift' -print0 \
  | xargs -0 grep -hE "$suite_class_pattern" \
  | sed -E "$suite_class_name" \
  | sort -u)

# A suite that drives RuntimeOwnerAuthorityTestFixture transitions the
# process-global owner authority through that same standard domain, so it
# belongs to the sequential cluster whether or not anyone remembered to list
# it. ChatToolExecutorPolicyTests did not, and a concurrent suite moving
# `auth_userId` underneath it failed its tool calls with
# `authorized_execution_owner_changed`, which blocked a release cut (#11511).
declare -a fixture_files=()
while IFS= read -r fixture_file; do
  fixture_files+=("$fixture_file")
done < <(find "$TESTS_ROOT" -type f -name '*.swift' \
  -exec grep -l 'RuntimeOwnerAuthorityTestFixture' {} +)

declare -a derived_serial_suites=()
if [ "${#fixture_files[@]}" -gt 0 ]; then
  while IFS= read -r suite; do
    derived_serial_suites+=("$suite")
  done < <(grep -hE "$suite_class_pattern" "${fixture_files[@]}" \
    | sed -E "$suite_class_name" \
    | sort -u)
fi

is_serial_suite() {
  case " $SERIAL_SUITES " in
    *" $1 "*) return 0 ;;
  esac
  local candidate
  for candidate in ${derived_serial_suites[@]+"${derived_serial_suites[@]}"}; do
    if [ "$candidate" = "$1" ]; then
      return 0
    fi
  done
  return 1
}

declare -a parallel_suites=()
declare -a serial_suites=()
for suite in "${suites[@]}"; do
  if is_serial_suite "$suite"; then
    serial_suites+=("$suite")
  else
    parallel_suites+=("$suite")
  fi
done

"$SKIP_RATCHET" --check --tests-root "$TESTS_ROOT"

cd "$MACOS_DIR"
suite_log_dir="$(mktemp -d)"
suite_worker_dir="$(mktemp -d)"
trap 'rm -rf "$suite_log_dir" "$suite_worker_dir"' EXIT
failed_suites=""
crashed_suites=""
suite_count="${#suites[@]}"
worker_count=0

if [[ "$PACKAGE_PATH" = /* ]]; then
  package_root="$PACKAGE_PATH"
else
  package_root="$MACOS_DIR/$PACKAGE_PATH"
fi

if [ "$PREBUILD" = "1" ] && [ "$suite_count" -gt 0 ]; then
  echo "Prebuilding Swift test bundle before parallel suite execution..."
  xcrun swift build --package-path "$PACKAGE_PATH" --build-tests
fi

# Only reports written after this point belong to the suite run; the prebuild
# and anything the runner did earlier must not be attributed to a crasher.
crash_marker="$suite_worker_dir/run-start"
touch "$crash_marker"

parallel_suite_count="${#parallel_suites[@]}"
if [ "$parallel_suite_count" -gt 0 ]; then
  worker_count="$WORKERS"
  if [ "$worker_count" -gt "$parallel_suite_count" ]; then
    worker_count="$parallel_suite_count"
  fi

  declare -a worker_lists=()
  declare -a worker_build_paths=()
  declare -a worker_runtime_paths=()
  declare -a worker_args=()
  for ((worker = 0; worker < worker_count; worker++)); do
    worker_lists+=("$suite_worker_dir/worker-$worker.suites")
    : >"${worker_lists[$worker]}"
    worker_build_paths+=("$suite_worker_dir/worker-$worker.build")
    worker_runtime_paths+=("$suite_worker_dir/worker-$worker.runtime")
  done

  for ((suite_index = 0; suite_index < parallel_suite_count; suite_index++)); do
    worker=$((suite_index % worker_count))
    printf '%s\n' "${parallel_suites[$suite_index]}" >>"${worker_lists[$worker]}"
  done

  for ((worker = 0; worker < worker_count; worker++)); do
    worker_build_path="${worker_build_paths[$worker]}"
    worker_runtime_path="${worker_runtime_paths[$worker]}"
    if [ "$PREBUILD" = "1" ]; then
      # `cp -c` requires a copy-on-write clone rather than silently creating
      # full physical copies. The hosted macOS runners use APFS; fail closed if
      # that contract changes so suite parallelism never raises runner minutes.
      cp -cR "$package_root/.build" "$worker_build_path"
    else
      mkdir -p "$worker_build_path"
    fi
    mkdir -p "$worker_runtime_path/home" "$worker_runtime_path/tmp"
    worker_args+=("${worker_lists[$worker]}" "$worker_build_path" "$worker_runtime_path")
  done

  printf '%s\0' "${worker_args[@]}" \
    | xargs -0 -n3 -P "$worker_count" "$SCRIPT_PATH" __run_worker "$suite_log_dir" || true
fi

# Run shared-auth-domain suites only after every parallel worker has exited.
# A distinct runtime per suite prevents sequential residue as well as races.
for ((serial_index = 0; serial_index < ${#serial_suites[@]}; serial_index++)); do
  suite="${serial_suites[$serial_index]}"
  serial_build_path="$suite_worker_dir/serial-$serial_index.build"
  serial_runtime_path="$suite_worker_dir/serial-$serial_index.runtime"
  if [ "$PREBUILD" = "1" ]; then
    cp -cR "$package_root/.build" "$serial_build_path"
  else
    mkdir -p "$serial_build_path"
  fi
  mkdir -p "$serial_runtime_path/home" "$serial_runtime_path/tmp"
  "$SCRIPT_PATH" __run_suite "$suite_log_dir" "$suite" "$serial_build_path" "$serial_runtime_path" || true
done
if [ "$worker_count" -eq 0 ] && [ "${#serial_suites[@]}" -gt 0 ]; then
  worker_count=1
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
    if grep -q "Exited with unexpected signal" "$suite_log_dir/$suite.log"; then
      crashed_suites="$crashed_suites $suite"
    fi
  fi
done

if [ -n "$crashed_suites" ]; then
  echo "Signal-killed Swift suites:$crashed_suites"
  dump_crash_reports "$crash_marker"
fi

echo "Ran $suite_count Swift suites in isolation with $worker_count worker(s), ${SUITE_TIMEOUT_SECONDS}s per-suite budget."

if [ -n "$failed_suites" ]; then
  echo "FAILED Swift suites:$failed_suites"
  exit 1
fi
