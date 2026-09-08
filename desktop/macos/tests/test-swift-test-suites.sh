#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
RUNNER="$MACOS_DIR/scripts/swift-test-suites.sh"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

TMPDIR="$(mktemp -d)"
cleanup() {
  rm -rf "$TMPDIR"
}
trap cleanup EXIT

mkdir -p "$TMPDIR/tests" "$TMPDIR/bin"
mkdir -p "$TMPDIR/package/.build/debug"
touch "$TMPDIR/package/.build/debug/test-bundle-placeholder"
cat >"$TMPDIR/tests/AlphaTests.swift" <<'SWIFT'
import XCTest
final class AlphaTests: XCTestCase {
    func testOne() {}
}
SWIFT
cat >"$TMPDIR/tests/BetaTests.swift" <<'SWIFT'
import XCTest
final class BetaTests: XCTestCase {
    func testOne() {}
}
SWIFT
cat >"$TMPDIR/tests/ChatDiscoverabilityTests.swift" <<'SWIFT'
import XCTest
final class ChatDiscoverabilityTests: XCTestCase {
    func testAgentControlCapabilitiesMatchCanonicalManifest() {}
    func testDesktopCapabilitiesExistInAgentToolDeclarations() {}
    func testDesktopPromptDistinguishesDelegationFromFloatingPills() {}
}
SWIFT
cat >"$TMPDIR/tests/APIClientRoutingTests.swift" <<'SWIFT'
import XCTest
final class APIClientRoutingTests: XCTestCase {
    func testDeleteConversationRoutesToPython() {}
}
SWIFT
cat >"$TMPDIR/tests/ActionItemsFTSRepairTests.swift" <<'SWIFT'
import XCTest
final class ActionItemsFTSRepairTests: XCTestCase {
    func testRepairToleratesMissingActionItemsFTSShadowTable() {}
}
SWIFT
cat >"$TMPDIR/tests/PiMonoWiringTests.swift" <<'SWIFT'
import XCTest
final class PiMonoWiringTests: XCTestCase {
    func testLocalAgentProviderDetectorMissingPromptIsUserFacing() {}
}
SWIFT
cat >"$TMPDIR/tests/AuthRefreshResilienceTests.swift" <<'SWIFT'
import XCTest
final class AuthRefreshResilienceTests: XCTestCase {
    func testOne() {}
}
SWIFT
cat >"$TMPDIR/tests/AuthTokenStorageTests.swift" <<'SWIFT'
import XCTest
final class AuthTokenStorageTests: XCTestCase {
    func testOne() {}
}
SWIFT
# Never listed in OMI_SWIFT_TEST_SERIAL_SUITES below: the runner must derive its
# sequential membership from the owner-authority fixture it drives.
cat >"$TMPDIR/tests/OwnerAuthorityAdopterTests.swift" <<'SWIFT'
import XCTest
final class OwnerAuthorityAdopterTests: XCTestCase {
    private var ownerFixture: RuntimeOwnerAuthorityTestFixture!
    func testOne() {}
}
SWIFT

cat >"$TMPDIR/bin/xcrun" <<'SH'
#!/usr/bin/env bash
set -euo pipefail

echo "$*" >>"$FAKE_XCRUN_LOG"
# The runner batches suites into ONE invocation carrying a repeated `--filter`,
# so this fixture must behave like SwiftPM: collect every filtered suite, and
# let any one of them decide the invocation's verdict.
suites=()
previous=""
for arg in "$@"; do
  if [ "$previous" = "--filter" ]; then
    suites+=("${arg%/}")
  fi
  previous="$arg"
done
suite="${suites[0]:-}"

has_suite() {
  local candidate
  for candidate in ${suites[@]+"${suites[@]}"}; do
    if [ "$candidate" = "$1" ]; then
      return 0
    fi
  done
  return 1
}

scratch_path=""
previous=""
for arg in "$@"; do
  if [ "$previous" = "--scratch-path" ]; then
    scratch_path="$arg"
    break
  fi
  previous="$arg"
done

if [[ "$*" == *"swift test"* ]]; then
  if [ -z "$scratch_path" ]; then
    echo "suite missing isolated scratch path" >&2
    exit 64
  fi
  # One row per filtered suite: the isolation assertions below are per suite and
  # must hold whether that suite ran alone or inside a batch.
  for filtered_suite in ${suites[@]+"${suites[@]}"}; do
    printf '%s\t%s\t%s\t%s\t%s\n' "$filtered_suite" "$scratch_path" "$HOME" "$CFFIXED_USER_HOME" "$TMPDIR" \
      >>"$FAKE_XCRUN_SCRATCH_LOG"
  done
  active_dir="$FAKE_XCRUN_SYNC_DIR/active"
  mkdir -p "$active_dir"
  active_marker="$active_dir/$$"
  trap 'rm -f "$active_marker"' EXIT
  touch "$active_marker"

  # Two workers are concurrent when two suite processes are alive at once.
  # Do not rendezvous on specific suite names: xargs -P 2 starts the first two
  # suites alphabetically, which are not guaranteed to be AlphaTests/BetaTests.
  active_count="$(find "$active_dir" -mindepth 1 -maxdepth 1 | wc -l | tr -d ' ')"
  if { has_suite AuthRefreshResilienceTests || has_suite AuthTokenStorageTests \
    || has_suite OwnerAuthorityAdopterTests; } \
    && [ "$active_count" -ge 2 ]; then
    touch "$FAKE_XCRUN_SYNC_DIR/serial-overlap"
  fi
  if [ "$active_count" -ge 2 ]; then
    touch "$FAKE_XCRUN_SYNC_DIR/overlap-proven"
  fi

  # Hold the worker briefly so a fast peer suite cannot finish before overlap
  # is observed when only two suites are in flight.
  sleep 0.1
fi

if has_suite AlphaTests; then
  echo "alpha failed"
  exit 42
fi

if has_suite CrasherTests; then
  suite=CrasherTests
  # What SwiftPM actually emits when the xctest host dies on a signal: the
  # signal line and nothing else. The crash reporter writes the frames.
  if [ -z "${FAKE_XCRUN_SKIP_CRASH_REPORT:-}" ]; then
    mkdir -p "$OMI_SWIFT_TEST_CRASH_REPORT_DIR"
    printf 'fixture crash report for %s\nThread 0 Crashed: SwiftUI layout frame\n' "$suite" \
      >"$OMI_SWIFT_TEST_CRASH_REPORT_DIR/xctest-fixture.ips"
  fi
  echo "error: Exited with unexpected signal code 11"
  exit 1
fi

if [ -n "${FAKE_XCRUN_HANG_SUITE:-}" ] && has_suite "$FAKE_XCRUN_HANG_SUITE"; then
  sleep 30 &
  child_pid=$!
  echo "$child_pid" >"$FAKE_XCRUN_HANG_CHILD_PID_PATH"
  wait "$child_pid"
fi

if [ -n "${FAKE_XCRUN_LOCKWAIT_SUITE:-}" ] && has_suite "$FAKE_XCRUN_LOCKWAIT_SUITE"; then
  # Park on the shared SwiftPM build lock (its wait message is the last log line)
  # for longer than the run budget, then proceed — the runner must not charge
  # this queue time against the per-suite timeout.
  echo "Another instance of SwiftPM is already running using '.build', waiting until that process has finished execution..."
  sleep "${FAKE_XCRUN_LOCKWAIT_SECONDS:-5}"
fi

if [ -n "${FAKE_XCRUN_SLOW_SUITE:-}" ] && has_suite "$FAKE_XCRUN_SLOW_SUITE"; then
  # Real work, not a hang: an invocation carrying this suite must be allowed to
  # finish under the budget the runner gave it.
  sleep "${FAKE_XCRUN_SLOW_SECONDS:-4}"
fi

for filtered_suite in ${suites[@]+"${suites[@]}"}; do
  echo "$filtered_suite passed"
done
SH
chmod +x "$TMPDIR/bin/xcrun"

export PATH="$TMPDIR/bin:$PATH"
export FAKE_XCRUN_LOG="$TMPDIR/xcrun.log"
export FAKE_XCRUN_SCRATCH_LOG="$TMPDIR/xcrun-scratch.log"
export FAKE_XCRUN_SYNC_DIR="$TMPDIR/xcrun-sync"
export OMI_SWIFT_TEST_DISCOVERY_ROOT="$TMPDIR/tests"
export OMI_SWIFT_TEST_PACKAGE_PATH="$TMPDIR/package"
export OMI_SWIFT_TEST_CRASH_REPORT_DIR="$TMPDIR/crash-reports"
export OMI_SWIFT_TEST_SUITE_WORKERS=2
export OMI_SWIFT_TEST_SERIAL_SUITES="AuthRefreshResilienceTests AuthTokenStorageTests"
# A batch's budget is the per-suite budget plus this allowance per additional
# suite. The fixture's suites are instant, and the timeout sections below assert
# on a 1s budget, so give a batch exactly the per-suite budget here: otherwise a
# batch carrying the hanging suite would outlive the budget under test and the
# timeout path would never be exercised.
export OMI_SWIFT_TEST_SUITE_BATCH_PER_SUITE_SECONDS=0
mkdir -p "$FAKE_XCRUN_SYNC_DIR"

if "$RUNNER" >"$TMPDIR/runner.out" 2>"$TMPDIR/runner.err"; then
  fail "runner unexpectedly succeeded despite AlphaTests failure"
fi

if [ ! -f "$FAKE_XCRUN_SYNC_DIR/overlap-proven" ]; then
  fail "runner did not execute suites concurrently with two workers"
fi
if ! grep -q -- "--- FAILED: AlphaTests ---" "$TMPDIR/runner.out"; then
  fail "runner did not print the failed suite heading"
fi
if ! grep -q "alpha failed" "$TMPDIR/runner.out"; then
  fail "runner did not preserve the failed suite log"
fi
if ! grep -q "Ran 9 Swift suites in isolation with 2 worker(s)." "$TMPDIR/runner.out"; then
  fail "runner did not report suite count and worker count"
fi
# Batching is the whole speed fix: a worker must put its suites into one
# SwiftPM invocation carrying a repeated `--filter`.
if ! awk '/swift test/ { if (gsub(/--filter/, "&") > 1) found = 1 } END { exit found ? 0 : 1 }' \
  "$FAKE_XCRUN_LOG"; then
  fail "runner never batched suites into a single SwiftPM invocation"
fi
# ...and a red batch must not smear its verdict across its members: only the
# suite that actually fails in isolation may be reported failed.
if ! grep -q -- "--- BATCH " "$TMPDIR/runner.out"; then
  fail "runner did not announce the failing batch's per-suite re-run"
fi
failed_headings="$(grep -c -- "--- FAILED: " "$TMPDIR/runner.out" | tr -d ' ')"
if [ "$failed_headings" != "1" ]; then
  fail "failing batch was attributed to $failed_headings suites; only AlphaTests fails in isolation"
fi
if [ -f "$FAKE_XCRUN_SYNC_DIR/serial-overlap" ]; then
  fail "shared-auth-domain suites overlapped another suite"
fi
derived_serial_scratch="$(awk -F '\t' '$1 == "OwnerAuthorityAdopterTests" {print $2}' \
  "$FAKE_XCRUN_SCRATCH_LOG")"
if [ -z "$derived_serial_scratch" ]; then
  fail "runner did not execute the owner-authority fixture suite"
fi
case "$derived_serial_scratch" in
  */serial-*.build) ;;
  *) fail "runner did not derive sequential execution from the owner-authority fixture" ;;
esac
if ! grep -q -- "--skip ChatDiscoverabilityTests/testAgentControlCapabilitiesMatchCanonicalManifest" "$FAKE_XCRUN_LOG"; then
  fail "runner did not pass ratcheted skips to SwiftPM"
fi
scratch_paths="$(awk -F '\t' '{print $2}' "$FAKE_XCRUN_SCRATCH_LOG" | sort -u | wc -l | tr -d ' ')"
if [ "$scratch_paths" -lt 2 ]; then
  fail "parallel suites did not receive distinct SwiftPM scratch directories"
fi
runtime_homes="$(awk -F '\t' '{print $4}' "$FAKE_XCRUN_SCRATCH_LOG" | sort -u | wc -l | tr -d ' ')"
if [ "$runtime_homes" -lt 2 ]; then
  fail "parallel suites did not receive distinct Foundation runtime homes"
fi
if ! awk -F '\t' '{ expected = $4; sub(/\/home$/, "/tmp", expected); if ($5 != expected) exit 1 }' \
  "$FAKE_XCRUN_SCRATCH_LOG"; then
  fail "runner did not isolate CoreFoundation preferences and temporary files per worker"
fi

# Local runs should get the same proven suite-level parallelism as CI unless a
# diagnosis explicitly asks for fewer workers.
unset OMI_SWIFT_TEST_SUITE_WORKERS SWIFT_TEST_SUITE_WORKERS
: >"$FAKE_XCRUN_LOG"
if "$RUNNER" >"$TMPDIR/default-runner.out" 2>"$TMPDIR/default-runner.err"; then
  fail "default runner unexpectedly succeeded despite AlphaTests failure"
fi
if ! grep -q "Ran 9 Swift suites in isolation with 4 worker(s)," "$TMPDIR/default-runner.out"; then
  fail "runner did not default local suite execution to four workers"
fi

# A discovery set made entirely of serial suites still executes with one
# effective worker and must not report the misleading zero-worker summary.
export OMI_SWIFT_TEST_SERIAL_SUITES="ActionItemsFTSRepairTests AlphaTests APIClientRoutingTests AuthRefreshResilienceTests AuthTokenStorageTests BetaTests ChatDiscoverabilityTests PiMonoWiringTests"
if "$RUNNER" >"$TMPDIR/all-serial-runner.out" 2>"$TMPDIR/all-serial-runner.err"; then
  fail "all-serial runner unexpectedly succeeded despite AlphaTests failure"
fi
if ! grep -q "Ran 9 Swift suites in isolation with 1 worker(s)," "$TMPDIR/all-serial-runner.out"; then
  fail "all-serial runner did not report one effective worker"
fi
export OMI_SWIFT_TEST_SERIAL_SUITES="AuthRefreshResilienceTests AuthTokenStorageTests"

# ...and the same per-suite budget as CI. A smaller local default is not a
# harmless local nicety: the slowest legitimate suite needs ~245s, so a 120s
# default reported the documented local runner FAILED on a clean main.
ci_workflow="$(cd "$MACOS_DIR/../.." && pwd)/.github/workflows/desktop-swift-ci.yml"
ci_budget="$(sed -n 's/^[[:space:]]*OMI_SWIFT_TEST_SUITE_TIMEOUT_SECONDS:[[:space:]]*"\{0,1\}\([0-9][0-9]*\)"\{0,1\}[[:space:]]*$/\1/p' "$ci_workflow" | head -1)"
[ -n "$ci_budget" ] || fail "could not read OMI_SWIFT_TEST_SUITE_TIMEOUT_SECONDS from $ci_workflow"
if ! grep -q "worker(s), ${ci_budget}s per-suite budget." "$TMPDIR/default-runner.out"; then
  fail "runner default per-suite budget does not match CI's ${ci_budget}s"
fi

export OMI_SWIFT_TEST_SUITE_TIMEOUT_SECONDS=1
export FAKE_XCRUN_HANG_SUITE=BetaTests
export FAKE_XCRUN_HANG_CHILD_PID_PATH="$TMPDIR/hanging-child.pid"
if "$RUNNER" >"$TMPDIR/timeout-runner.out" 2>"$TMPDIR/timeout-runner.err"; then
  fail "timeout fixture unexpectedly succeeded"
fi
if ! grep -q -- "--- FAILED: BetaTests ---" "$TMPDIR/timeout-runner.out"; then
  fail "runner did not identify the timed-out suite"
fi
if ! grep -q "suite timed out after 1s" "$TMPDIR/timeout-runner.out"; then
  fail "runner did not report the per-suite timeout"
fi
if [ ! -s "$FAKE_XCRUN_HANG_CHILD_PID_PATH" ]; then
  fail "timeout fixture did not record its descendant process"
fi
hanging_child_pid="$(cat "$FAKE_XCRUN_HANG_CHILD_PID_PATH")"
if kill -0 "$hanging_child_pid" 2>/dev/null; then
  fail "runner left the timed-out suite's descendant process alive"
fi

# A suite parked on the shared SwiftPM build lock must not spend its run budget:
# with a 2s budget it still passes after a 5s lock wait. (AlphaTests still fails
# with exit 42, so the runner exits non-zero overall — assert on BetaTests only.)
unset FAKE_XCRUN_HANG_SUITE
export OMI_SWIFT_TEST_SUITE_TIMEOUT_SECONDS=2
export FAKE_XCRUN_LOCKWAIT_SUITE=BetaTests
export FAKE_XCRUN_LOCKWAIT_SECONDS=5
"$RUNNER" >"$TMPDIR/lockwait-runner.out" 2>"$TMPDIR/lockwait-runner.err" || true
if grep -q -- "--- FAILED: BetaTests ---" "$TMPDIR/lockwait-runner.out"; then
  fail "runner charged SwiftPM build-lock wait against the per-suite run budget"
fi

# A suite killed by a signal leaves no frames in SwiftPM's log, and the hosted
# runner's crash reports die with the machine. The runner must surface them
# next to the failing suite or a CI-only crasher stays undiagnosable (#11573).
unset FAKE_XCRUN_LOCKWAIT_SUITE FAKE_XCRUN_LOCKWAIT_SECONDS
unset OMI_SWIFT_TEST_SUITE_TIMEOUT_SECONDS
cat >"$TMPDIR/tests/CrasherTests.swift" <<'SWIFT'
import XCTest
final class CrasherTests: XCTestCase {
    func testOne() {}
}
SWIFT
if "$RUNNER" >"$TMPDIR/crash-runner.out" 2>"$TMPDIR/crash-runner.err"; then
  fail "crash fixture unexpectedly succeeded"
fi
if ! grep -q "Signal-killed Swift suites: CrasherTests" "$TMPDIR/crash-runner.out"; then
  fail "runner did not name the signal-killed suite"
fi
if ! grep -q -- "--- CRASH REPORT: " "$TMPDIR/crash-runner.out"; then
  fail "runner did not surface the crash report for a signal-killed suite"
fi
if ! grep -q "Thread 0 Crashed: SwiftUI layout frame" "$TMPDIR/crash-runner.out"; then
  fail "runner did not print the crash report's contents"
fi

# A report predating the run belongs to some earlier process; attributing it to
# this run's crasher would send the next reader after the wrong backtrace.
rm -f "$OMI_SWIFT_TEST_CRASH_REPORT_DIR/xctest-fixture.ips"
printf 'stale report\n' >"$OMI_SWIFT_TEST_CRASH_REPORT_DIR/xctest-stale.ips"
touch -t 202001010000 "$OMI_SWIFT_TEST_CRASH_REPORT_DIR/xctest-stale.ips"
export FAKE_XCRUN_SKIP_CRASH_REPORT=1
if "$RUNNER" >"$TMPDIR/stale-crash-runner.out" 2>"$TMPDIR/stale-crash-runner.err"; then
  fail "stale-report fixture unexpectedly succeeded"
fi
if grep -q "stale report" "$TMPDIR/stale-crash-runner.out"; then
  fail "runner attributed a pre-run crash report to this run"
fi
if ! grep -q "No crash reports newer than this run" "$TMPDIR/stale-crash-runner.out"; then
  fail "runner did not report the absence of a fresh crash report"
fi

# An all-green worker must pay SwiftPM's ~5s startup once, not once per suite:
# that overhead, not the tests, was ~28.7 min of the hosted macOS suite job.
# With one worker and a batch size covering the discovery set, every parallel
# suite is selected by a single `swift test` process.
unset FAKE_XCRUN_SKIP_CRASH_REPORT
mkdir -p "$TMPDIR/green-tests"
cp "$TMPDIR"/tests/*.swift "$TMPDIR/green-tests/"
rm -f "$TMPDIR/green-tests/AlphaTests.swift" "$TMPDIR/green-tests/CrasherTests.swift"
export OMI_SWIFT_TEST_DISCOVERY_ROOT="$TMPDIR/green-tests"
export OMI_SWIFT_TEST_SUITE_WORKERS=1
: >"$FAKE_XCRUN_LOG"
if ! "$RUNNER" >"$TMPDIR/batch-runner.out" 2>"$TMPDIR/batch-runner.err"; then
  fail "all-green discovery set did not pass through the batch fast path"
fi
if ! grep -q "Ran 8 Swift suites in isolation with 1 worker(s)," "$TMPDIR/batch-runner.out"; then
  fail "batch fast path did not report the whole discovery set"
fi
if ! grep -q "batches of up to 25 suite(s) per SwiftPM process" "$TMPDIR/batch-runner.out"; then
  fail "summary line does not report the batch size actually used"
fi
if grep -q -- "--- BATCH " "$TMPDIR/batch-runner.out"; then
  fail "a passing batch fell back to per-suite execution"
fi
# Five parallel suites in one invocation, plus the three sequential ones.
batch_filters="$(awk '/swift test/ { n = gsub(/--filter/, "&"); if (n > max) max = n } END { print max + 0 }' \
  "$FAKE_XCRUN_LOG")"
if [ "$batch_filters" != "5" ]; then
  fail "batch selected $batch_filters suites in one invocation, expected all 5 parallel suites"
fi
green_invocations="$(grep -c "swift test" "$FAKE_XCRUN_LOG" | tr -d ' ')"
if [ "$green_invocations" != "4" ]; then
  fail "green run used $green_invocations SwiftPM invocations, expected 1 batch + 3 sequential suites"
fi

# A batch gets the per-suite budget PLUS an allowance for every additional suite
# it carries. Charging a batch one suite's budget would kill healthy batches as
# soon as the suite count grew, and the fallback would then re-run all of them —
# slower than never batching at all. Five suites at a 1s per-suite budget and a
# 3s allowance give the batch 13s, so a 4s suite inside it must survive.
export OMI_SWIFT_TEST_SUITE_TIMEOUT_SECONDS=1
export OMI_SWIFT_TEST_SUITE_BATCH_PER_SUITE_SECONDS=3
export FAKE_XCRUN_SLOW_SUITE=BetaTests
export FAKE_XCRUN_SLOW_SECONDS=4
if ! "$RUNNER" >"$TMPDIR/batch-budget-runner.out" 2>"$TMPDIR/batch-budget-runner.err"; then
  fail "batch was killed at the single-suite budget instead of its scaled batch budget"
fi
if grep -q -- "--- BATCH " "$TMPDIR/batch-budget-runner.out"; then
  fail "batch budget did not cover a legitimately slow suite; it fell back to per-suite runs"
fi
unset FAKE_XCRUN_SLOW_SUITE FAKE_XCRUN_SLOW_SECONDS OMI_SWIFT_TEST_SUITE_TIMEOUT_SECONDS
export OMI_SWIFT_TEST_SUITE_BATCH_PER_SUITE_SECONDS=0

# A red batch is never authoritative: every suite it carried is re-run through
# the isolated per-suite path, and only what fails there is reported failed.
mkdir -p "$TMPDIR/fallback-tests"
cp "$TMPDIR"/green-tests/*.swift "$TMPDIR/fallback-tests/"
cp "$TMPDIR/tests/AlphaTests.swift" "$TMPDIR/fallback-tests/"
export OMI_SWIFT_TEST_DISCOVERY_ROOT="$TMPDIR/fallback-tests"
: >"$FAKE_XCRUN_LOG"
if "$RUNNER" >"$TMPDIR/fallback-runner.out" 2>"$TMPDIR/fallback-runner.err"; then
  fail "batch fallback runner unexpectedly succeeded despite AlphaTests failure"
fi
if ! grep -q -- "--- BATCH worker-0-0 exited 42; re-running its 6 suite(s) in isolation ---" \
  "$TMPDIR/fallback-runner.out"; then
  fail "runner did not report the failing batch and its isolated re-run"
fi
failed_headings="$(grep -c -- "--- FAILED: " "$TMPDIR/fallback-runner.out" | tr -d ' ')"
if [ "$failed_headings" != "1" ]; then
  fail "batch failure was attributed to $failed_headings suites, expected AlphaTests alone"
fi
if ! grep -q -- "--- FAILED: AlphaTests ---" "$TMPDIR/fallback-runner.out"; then
  fail "batch fallback lost the failing suite's identity"
fi
if ! grep -q "FAILED Swift suites: AlphaTests" "$TMPDIR/fallback-runner.out"; then
  fail "batch fallback did not report AlphaTests as the only failed suite"
fi
if ! awk '/swift test/ && /--filter AlphaTests\// { if (gsub(/--filter/, "&") == 1) found = 1 } END { exit found ? 0 : 1 }' \
  "$FAKE_XCRUN_LOG"; then
  fail "failing suite was never re-run as an isolated single-suite invocation"
fi
# 1 batch + 6 isolated re-runs + 3 sequential suites: the fallback re-establishes
# isolation for every member of the batch, not only for the failing one.
fallback_invocations="$(grep -c "swift test" "$FAKE_XCRUN_LOG" | tr -d ' ')"
if [ "$fallback_invocations" != "10" ]; then
  fail "batch fallback used $fallback_invocations SwiftPM invocations, expected 1 + 6 + 3"
fi

# The escape hatch for a diagnosis: batch size 1 must be exactly the historical
# one-process-per-suite behaviour — no combined invocation, and no suite run
# twice through a batch and then again in the fallback.
export OMI_SWIFT_TEST_SUITE_BATCH_SIZE=1
: >"$FAKE_XCRUN_LOG"
if "$RUNNER" >"$TMPDIR/unbatched-runner.out" 2>"$TMPDIR/unbatched-runner.err"; then
  fail "unbatched runner unexpectedly succeeded despite AlphaTests failure"
fi
if ! awk '/swift test/ { if (gsub(/--filter/, "&") != 1) exit 1 }' "$FAKE_XCRUN_LOG"; then
  fail "OMI_SWIFT_TEST_SUITE_BATCH_SIZE=1 still combined suites into one invocation"
fi
if grep -q -- "--- BATCH " "$TMPDIR/unbatched-runner.out"; then
  fail "OMI_SWIFT_TEST_SUITE_BATCH_SIZE=1 went through the batch fallback path"
fi
unbatched_invocations="$(grep -c "swift test" "$FAKE_XCRUN_LOG" | tr -d ' ')"
if [ "$unbatched_invocations" != "9" ]; then
  fail "unbatched run used $unbatched_invocations SwiftPM invocations, expected one per suite"
fi
if ! grep -q "batches of up to 1 suite(s) per SwiftPM process" "$TMPDIR/unbatched-runner.out"; then
  fail "summary line did not report the configured batch size"
fi
unbatched_failed="$(grep -c -- "--- FAILED: " "$TMPDIR/unbatched-runner.out" | tr -d ' ')"
if [ "$unbatched_failed" != "1" ] || ! grep -q -- "--- FAILED: AlphaTests ---" "$TMPDIR/unbatched-runner.out"; then
  fail "unbatched run did not reproduce the per-suite failure attribution"
fi

# A measure-block suite is derived as batch-ineligible: it runs its blocks ten
# times and legitimately takes minutes, so co-residency either blows a healthy
# batch's budget (observed on CI: a 17-minute batch timeout followed by the
# full 25-suite isolated fallback) or forces every batch's budget up to the
# worst suite. It must run in its own SwiftPM process while its neighbours
# still batch.
export OMI_SWIFT_TEST_SUITE_BATCH_SIZE=25
mkdir -p "$TMPDIR/solo-tests"
cp "$TMPDIR"/green-tests/*.swift "$TMPDIR/solo-tests/"
cat >"$TMPDIR/solo-tests/AtlasPerfHarnessTests.swift" <<'SWIFT'
import XCTest

final class AtlasPerfHarnessTests: XCTestCase {
  func testLayoutThroughput() {
    measure({})
  }
}
SWIFT
export OMI_SWIFT_TEST_DISCOVERY_ROOT="$TMPDIR/solo-tests"
: >"$FAKE_XCRUN_LOG"
if ! "$RUNNER" >"$TMPDIR/solo-runner.out" 2>"$TMPDIR/solo-runner.err"; then
  fail "discovery set with a measure suite did not pass"
fi
if ! grep -q "Ran 9 Swift suites in isolation" "$TMPDIR/solo-runner.out"; then
  fail "solo scenario did not report the whole discovery set"
fi
if grep -q -- "--- BATCH " "$TMPDIR/solo-runner.out"; then
  fail "solo scenario fell back to per-suite execution"
fi
if ! awk '/swift test/ && /--filter AtlasPerfHarnessTests\// { if (gsub(/--filter/, "&") == 1) found = 1 } END { exit found ? 0 : 1 }' \
  "$FAKE_XCRUN_LOG"; then
  fail "measure suite was not isolated into its own single-filter invocation"
fi
if awk '/swift test/ && /--filter AtlasPerfHarnessTests\// { if (gsub(/--filter/, "&") > 1) shared = 1 } END { exit shared ? 1 : 0 }' \
  "$FAKE_XCRUN_LOG"; then
  :
else
  fail "measure suite shared a batch with other suites"
fi
# 1 batch of the 5 ordinary parallel suites + 1 solo + 3 sequential.
solo_invocations="$(grep -c "swift test" "$FAKE_XCRUN_LOG" | tr -d ' ')"
if [ "$solo_invocations" != "5" ]; then
  fail "solo scenario used $solo_invocations SwiftPM invocations, expected 1 batch + 1 solo + 3 sequential"
fi

echo "swift-test-suites tests passed"
