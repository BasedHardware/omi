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
# One `xcrun swift test` invocation spends ~5.1s in SwiftPM before a single test
# runs. Across ~674 discovered suites that startup cost, not the tests, was the
# largest consumer of hosted macOS runner minutes (~28.7 min of wall clock on
# CI's two workers). So a worker executes its suites in batches: ONE SwiftPM
# process carrying one `--filter Suite/` argument per suite (SwiftPM ORs
# repeated --filter flags; a single giant regex would be one unreadable
# argument with different escaping hazards).
#
# Why this is safe: batching is optimistic only. A batch verdict is never
# authoritative for a failure — a batch that exits non-zero or times out is
# discarded and every suite it carried is re-run through the per-suite path,
# which keeps today's isolation, today's per-suite budget, and today's failure
# attribution for anything red. Only the all-green path is fast.
#
# Known trade-off: a batch that PASSES can mask an order dependence between two
# of its suites that per-suite isolation would have caught, because those suites
# shared one process. That is the price of the startup saving. It cannot
# misattribute a failure, because the moment a batch is red the fallback
# re-establishes isolation for every suite in it. The serial cluster below
# (shared UserDefaults auth domain) is never batched, and
# OMI_SWIFT_TEST_SUITE_BATCH_SIZE=1 restores one-process-per-suite exactly for a
# diagnosis.
SUITE_BATCH_SIZE="${OMI_SWIFT_TEST_SUITE_BATCH_SIZE:-25}"
# A batch pays SwiftPM startup once, so its budget is the per-suite budget plus
# an execution allowance for each ADDITIONAL suite it carries. The allowance
# only has to cover run time, not startup.
SUITE_BATCH_PER_SUITE_SECONDS="${OMI_SWIFT_TEST_SUITE_BATCH_PER_SUITE_SECONDS:-30}"
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

# Runs ONE `xcrun swift test` invocation covering one or more suites under the
# shared watchdog, writing its combined output to `log_path`. Touches
# `${log_path%.log}.timeout` when the watchdog killed the invocation, and
# returns the invocation's exit status. Both the per-suite path and the batch
# path go through here so they cannot drift apart on isolation or on the
# build-lock exemption.
run_swift_test() {
  local log_path="$1"
  local budget_seconds="$2"
  local build_path="$3"
  local runtime_path="$4"
  shift 4
  local timeout_path="${log_path%.log}.timeout"
  local -a filter_args=()
  local -a skip_args=()
  local suite skip_arg

  for suite in "$@"; do
    filter_args+=(--filter "${suite}/")
    # Every skip id is `Suite/testMethod`, so per-suite skip sets are disjoint
    # by construction: a batch carries their union with no possible collision.
    while IFS= read -r skip_arg; do
      skip_args+=("$skip_arg")
    done < <("$SKIP_RATCHET" --args-for-suite "$suite")
  done
  local -a build_args=()
  if [ "$PREBUILD" = "1" ]; then
    build_args+=("--skip-build")
  fi
  local -a command=(
    xcrun swift test --package-path "$PACKAGE_PATH" --scratch-path "$build_path"
  )
  # Bash 3.2 (the system bash on hosted runners) treats "${empty[@]}" as an
  # unbound variable under `set -u`, so an empty array must never be expanded
  # inline — with OMI_SWIFT_TEST_PREBUILD=0 that killed every suite process
  # before it ran.
  if [ "${#build_args[@]}" -gt 0 ]; then
    command+=("${build_args[@]}")
  fi
  command+=("${filter_args[@]}")
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
    local remaining="$budget_seconds"
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
  set -e
  return "$status"
}

# One suite, one SwiftPM process, one status file. This is the authoritative
# path: it owns failure attribution and the isolation semantics every red suite
# is judged by.
run_suite() {
  local log_dir="$1"
  local suite="$2"
  local build_path="$3"
  local runtime_path="$4"
  local log_path="$log_dir/$suite.log"
  local status_path="$log_dir/$suite.status"
  local timeout_path="$log_dir/$suite.timeout"
  local status=0
  local budget="$SUITE_TIMEOUT_SECONDS"

  # A measure-block suite's wall clock scales with runner contention: the
  # MemoryAtlas harness needs ~245s alone, and a third worker on a 3-core
  # hosted Mac can push it past the flat budget. Double the budget for the
  # solo cluster rather than raising it for all ~670 suites, where it would
  # let a genuine hang burn ten minutes instead of five.
  if is_solo_suite "$suite"; then
    budget=$((SUITE_TIMEOUT_SECONDS * 2))
  fi

  rm -f "$timeout_path"
  run_swift_test "$log_path" "$budget" "$build_path" "$runtime_path" "$suite" || status=$?
  if [ -f "$timeout_path" ]; then
    echo "suite timed out after ${budget}s" >>"$log_path"
    status=124
  fi
  echo "$status" >"$status_path"
  exit "$status"
}

# Many suites, one SwiftPM process — the green fast path. A pass marks every
# suite in the batch green; anything else is thrown away and re-run per suite.
run_batch() {
  local log_dir="$1"
  local batch_id="$2"
  local build_path="$3"
  local runtime_path="$4"
  shift 4
  local -a batch_suites=("$@")
  local batch_size="${#batch_suites[@]}"
  local log_path="$log_dir/batch-$batch_id.log"
  local timeout_path="$log_dir/batch-$batch_id.timeout"
  local budget=$((SUITE_TIMEOUT_SECONDS + (batch_size - 1) * SUITE_BATCH_PER_SUITE_SECONDS))
  local status=0
  local suite

  rm -f "$timeout_path"
  run_swift_test "$log_path" "$budget" "$build_path" "$runtime_path" "${batch_suites[@]}" || status=$?
  if [ -f "$timeout_path" ]; then
    echo "batch of ${batch_size} suite(s) timed out after ${budget}s" >>"$log_path"
    status=124
  fi

  if [ "$status" = "0" ]; then
    # Write the per-suite status files the reporting loop reads, and point each
    # suite's log at the batch's combined output so nothing downstream has to
    # know a batch happened.
    for suite in "${batch_suites[@]}"; do
      echo "$suite passed in batch $batch_id; combined output: $log_path" >"$log_dir/$suite.log"
      echo "0" >"$log_dir/$suite.status"
    done
    exit 0
  fi

  # A batch is only ever evidence that something in it needs isolating. Re-run
  # every member on the per-suite path — same budget, same isolated status and
  # log files — and let those results stand. If none of them reproduces the
  # failure, the batch hit an order dependence between two suites that share a
  # process; the run stays green, matching the isolated verdict, and this line
  # is the trail back to it.
  echo "--- BATCH $batch_id exited $status; re-running its ${batch_size} suite(s) in isolation ---"
  echo "batch suites: ${batch_suites[*]}"
  for suite in "${batch_suites[@]}"; do
    "$SCRIPT_PATH" __run_suite "$log_dir" "$suite" "$build_path" "$runtime_path" || true
  done
  exit 0
}

# Suites the parent resolved as batch-ineligible (see the derivation near
# discovery). Workers are child processes, so the resolved list travels in an
# exported environment variable, not in shell state.
is_solo_suite() {
  case " ${OMI_SWIFT_TEST_SOLO_SUITES_RESOLVED:-} " in
    *" $1 "*) return 0 ;;
  esac
  return 1
}

run_worker() {
  local log_dir="$1"
  local suite_list="$2"
  local build_path="$3"
  local runtime_path="$4"
  local suite
  local -a pending=()

  # Suites retain their process isolation on every failure path, but a worker
  # owns one cloned SwiftPM scratch directory. This avoids the shared `.build`
  # lock that made CI's original parallel runner report queued suites as false
  # timeouts. The worker also owns its process-global Foundation state, and its
  # batches inherit that same isolation.
  while IFS= read -r suite; do
    pending+=("$suite")
  done <"$suite_list"

  local total="${#pending[@]}"
  local batch_label
  batch_label="$(basename "$suite_list")"
  batch_label="${batch_label%.suites}"
  local index=0
  local batch_index=0
  local -a batch=()
  while [ "$index" -lt "$total" ]; do
    batch=()
    while [ "${#batch[@]}" -lt "$SUITE_BATCH_SIZE" ] && [ "$index" -lt "$total" ]; do
      suite="${pending[$index]}"
      index=$((index + 1))
      if is_solo_suite "$suite"; then
        # A measure-block suite legitimately runs for minutes; sharing a batch
        # budget with it either kills a healthy batch or inflates every batch's
        # budget to cover the worst suite. It keeps its own process and its own
        # per-suite budget.
        "$SCRIPT_PATH" __run_suite "$log_dir" "$suite" "$build_path" "$runtime_path" || true
        continue
      fi
      batch+=("$suite")
    done
    if [ "${#batch[@]}" -eq 0 ]; then
      continue
    fi
    if [ "${#batch[@]}" -eq 1 ]; then
      # A single-suite batch is the per-suite path with extra steps, and going
      # through the batch wrapper would run a failing suite twice. Dispatching
      # it directly is what makes OMI_SWIFT_TEST_SUITE_BATCH_SIZE=1 reproduce
      # the historical behaviour exactly.
      "$SCRIPT_PATH" __run_suite "$log_dir" "${batch[0]}" "$build_path" "$runtime_path" || true
    else
      "$SCRIPT_PATH" __run_batch "$log_dir" "$batch_label-$batch_index" \
        "$build_path" "$runtime_path" "${batch[@]}" || true
    fi
    batch_index=$((batch_index + 1))
  done
}

if [ "${1:-}" = "__run_suite" ]; then
  run_suite "$2" "$3" "$4" "$5"
fi

if [ "${1:-}" = "__run_batch" ]; then
  shift
  run_batch "$@"
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
[[ "$SUITE_BATCH_SIZE" =~ ^[0-9]+$ ]] \
  || fail "OMI_SWIFT_TEST_SUITE_BATCH_SIZE must be a positive integer, got '$SUITE_BATCH_SIZE'"
if [ "$SUITE_BATCH_SIZE" -lt 1 ]; then
  fail "OMI_SWIFT_TEST_SUITE_BATCH_SIZE must be at least 1 (1 runs one suite per SwiftPM process)"
fi
[[ "$SUITE_BATCH_PER_SUITE_SECONDS" =~ ^[0-9]+$ ]] \
  || fail "OMI_SWIFT_TEST_SUITE_BATCH_PER_SUITE_SECONDS must be a non-negative integer, got '$SUITE_BATCH_PER_SUITE_SECONDS'"

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

# XCTest `measure` suites run their blocks ten times and legitimately take
# minutes each. Discovery order is alphabetical, so naive chunking concentrated
# the MemoryAtlas performance cluster into one batch that blew a 17-minute
# batch budget and then paid the full isolated fallback on top (CI run
# 2026-08-26, batch worker-0-8 exited 124). Derive them from the source —
# like the serial cluster above, so a new measure suite cannot silently join
# the batch pool — and run each in its own SwiftPM process, where the startup
# cost batching saves is noise next to the suite's run time.
declare -a measure_files=()
while IFS= read -r measure_file; do
  measure_files+=("$measure_file")
done < <(find "$TESTS_ROOT" -type f -name '*.swift' \
  -exec grep -lE '\bmeasure(Metrics)?\(' {} + 2>/dev/null || true)

derived_solo_suites=""
if [ "${#measure_files[@]}" -gt 0 ]; then
  derived_solo_suites="$(grep -hE "$suite_class_pattern" "${measure_files[@]}" \
    | sed -E "$suite_class_name" \
    | sort -u | tr '\n' ' ')"
fi
export OMI_SWIFT_TEST_SOLO_SUITES_RESOLVED="${OMI_SWIFT_TEST_SOLO_SUITES:-} $derived_solo_suites"

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
# These are never batched: batching would put two of them in one process, which
# is precisely the sharing this cluster exists to prevent (#11511).
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

echo "Ran $suite_count Swift suites in isolation with $worker_count worker(s), ${SUITE_TIMEOUT_SECONDS}s per-suite budget, batches of up to ${SUITE_BATCH_SIZE} suite(s) per SwiftPM process (any failing batch re-runs per suite)."

if [ -n "$failed_suites" ]; then
  echo "FAILED Swift suites:$failed_suites"
  exit 1
fi
