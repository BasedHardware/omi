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

if [ "$suite" = "AlphaTests" ] || [ "$suite" = "BetaTests" ]; then
  peer="AlphaTests"
  if [ "$suite" = "AlphaTests" ]; then
    peer="BetaTests"
  fi

  entered_path="$FAKE_XCRUN_SYNC_DIR/$suite.entered"
  peer_entered_path="$FAKE_XCRUN_SYNC_DIR/$peer.entered"
  trap 'rm -f "$entered_path"' EXIT
  touch "$entered_path"

  # This is a deadlock guard, not the concurrency oracle. Reaching the peer's
  # marker proves it entered while this process was still active and waiting.
  deadline=$((SECONDS + 10))
  while [ ! -f "$peer_entered_path" ]; do
    if [ "$SECONDS" -ge "$deadline" ]; then
      echo "rendezvous timed out waiting for $peer" >&2
      exit 1
    fi
    sleep 0.05
  done
  touch "$FAKE_XCRUN_SYNC_DIR/overlap-proven"
fi

if [ "$suite" = "AlphaTests" ]; then
  echo "alpha failed"
  exit 42
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
  fail "runner did not execute AlphaTests and BetaTests concurrently"
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

echo "swift-test-suites tests passed"
