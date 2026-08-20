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
filter=""
previous=""
for arg in "$@"; do
  if [ "$previous" = "--filter" ]; then
    filter="$arg"
    break
  fi
  previous="$arg"
done
suite="${filter%/}"

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
  printf '%s\t%s\t%s\t%s\t%s\n' "$suite" "$scratch_path" "$HOME" "$CFFIXED_USER_HOME" "$TMPDIR" \
    >>"$FAKE_XCRUN_SCRATCH_LOG"
  active_dir="$FAKE_XCRUN_SYNC_DIR/active"
  mkdir -p "$active_dir"
  active_marker="$active_dir/$$"
  trap 'rm -f "$active_marker"' EXIT
  touch "$active_marker"

  # Two workers are concurrent when two suite processes are alive at once.
  # Do not rendezvous on specific suite names: xargs -P 2 starts the first two
  # suites alphabetically, which are not guaranteed to be AlphaTests/BetaTests.
  active_count="$(find "$active_dir" -mindepth 1 -maxdepth 1 | wc -l | tr -d ' ')"
  if [[ "$suite" == AuthRefreshResilienceTests || "$suite" == AuthTokenStorageTests \
    || "$suite" == OwnerAuthorityAdopterTests ]] \
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

if [ "$suite" = "AlphaTests" ]; then
  echo "alpha failed"
  exit 42
fi

if [ "$suite" = "CrasherTests" ]; then
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

if [ -n "${FAKE_XCRUN_HANG_SUITE:-}" ] && [ "$FAKE_XCRUN_HANG_SUITE" = "$suite" ]; then
  sleep 30 &
  child_pid=$!
  echo "$child_pid" >"$FAKE_XCRUN_HANG_CHILD_PID_PATH"
  wait "$child_pid"
fi

if [ -n "${FAKE_XCRUN_LOCKWAIT_SUITE:-}" ] && [ "$FAKE_XCRUN_LOCKWAIT_SUITE" = "$suite" ]; then
  # Park on the shared SwiftPM build lock (its wait message is the last log line)
  # for longer than the run budget, then proceed — the runner must not charge
  # this queue time against the per-suite timeout.
  echo "Another instance of SwiftPM is already running using '.build', waiting until that process has finished execution..."
  sleep "${FAKE_XCRUN_LOCKWAIT_SECONDS:-5}"
fi

echo "$suite passed"
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

echo "swift-test-suites tests passed"
