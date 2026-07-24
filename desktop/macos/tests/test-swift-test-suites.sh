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

if [[ "$*" == *"swift test"* ]]; then
  active_dir="$FAKE_XCRUN_SYNC_DIR/active"
  mkdir -p "$active_dir"
  active_marker="$active_dir/$$"
  trap 'rm -f "$active_marker"' EXIT
  touch "$active_marker"

  # Two workers are concurrent when two suite processes are alive at once.
  # Do not rendezvous on specific suite names: xargs -P 2 starts the first two
  # suites alphabetically, which are not guaranteed to be AlphaTests/BetaTests.
  active_count="$(find "$active_dir" -mindepth 1 -maxdepth 1 | wc -l | tr -d ' ')"
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
export FAKE_XCRUN_SYNC_DIR="$TMPDIR/xcrun-sync"
export OMI_SWIFT_TEST_DISCOVERY_ROOT="$TMPDIR/tests"
export OMI_SWIFT_TEST_PACKAGE_PATH="$TMPDIR/package"
export OMI_SWIFT_TEST_SUITE_WORKERS=2
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
if ! grep -q "Ran 6 Swift suites in isolation with 2 worker(s)." "$TMPDIR/runner.out"; then
  fail "runner did not report suite count and worker count"
fi
if ! grep -q -- "--skip ChatDiscoverabilityTests/testAgentControlCapabilitiesMatchCanonicalManifest" "$FAKE_XCRUN_LOG"; then
  fail "runner did not pass ratcheted skips to SwiftPM"
fi

# Local runs should get the same proven suite-level parallelism as CI unless a
# diagnosis explicitly asks for fewer workers.
unset OMI_SWIFT_TEST_SUITE_WORKERS SWIFT_TEST_SUITE_WORKERS
: >"$FAKE_XCRUN_LOG"
if "$RUNNER" >"$TMPDIR/default-runner.out" 2>"$TMPDIR/default-runner.err"; then
  fail "default runner unexpectedly succeeded despite AlphaTests failure"
fi
if ! grep -q "Ran 6 Swift suites in isolation with 4 worker(s)." "$TMPDIR/default-runner.out"; then
  fail "runner did not default local suite execution to four workers"
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

echo "swift-test-suites tests passed"
