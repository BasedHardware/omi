#!/usr/bin/env bash
# Shard run directories stay on the build's volume. A run directory on another
# volume warns and does not copy the prebuilt scratch.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
RUNNER="$MACOS_DIR/scripts/swift-test-suites.sh"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

if [ "$(uname -s)" != "Darwin" ]; then
  echo "swift test shard volume tests skipped (not Darwin)"
  exit 0
fi

ROOT="$(mktemp -d "${TMPDIR:-/tmp}/swift-shard-volume.XXXXXX")"
DATA="$(mktemp -d /private/tmp/swift-shard-volume.XXXXXX)"
cleanup() {
  rm -rf "$ROOT" "$DATA"
}
trap cleanup EXIT

scratch_dev="$(stat -L -f '%d' "$ROOT")"
data_dev="$(stat -L -f '%d' "$DATA")"
[ "$scratch_dev" != "$data_dev" ] || {
  echo "swift test shard volume tests skipped (TMPDIR and /private/tmp share a device)"
  exit 0
}

mkdir -p "$ROOT/tests" "$ROOT/package/.build" "$ROOT/bin" "$ROOT/same-shards" "$DATA/shards"
printf 'marker-v1\n' >"$ROOT/package/.build/marker.txt"
cat >"$ROOT/tests/AlphaTests.swift" <<'SWIFT'
import XCTest
final class AlphaTests: XCTestCase {
    func testOne() {}
}
SWIFT
cat >"$ROOT/tests/ChatDiscoverabilityTests.swift" <<'SWIFT'
import XCTest
final class ChatDiscoverabilityTests: XCTestCase {
    func testAgentControlCapabilitiesMatchCanonicalManifest() {}
    func testDesktopCapabilitiesExistInAgentToolDeclarations() {}
}
SWIFT
cat >"$ROOT/tests/APIClientRoutingTests.swift" <<'SWIFT'
import XCTest
final class APIClientRoutingTests: XCTestCase {
    func testDeleteConversationRoutesToPython() {}
}
SWIFT
cat >"$ROOT/bin/xcrun" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >>"${FAKE_XCRUN_LOG:?}"
scratch=""
skip=0
prev=""
for arg in "$@"; do
  if [ "$prev" = "--scratch-path" ]; then
    scratch="$arg"
  fi
  if [ "$arg" = "--skip-build" ]; then
    skip=1
  fi
  prev="$arg"
done
if [ -n "$scratch" ]; then
  if [ -f "$scratch/marker.txt" ]; then
    printf 'marker\n' >>"${FAKE_XCRUN_LOG:?}"
  else
    printf 'no-marker\n' >>"${FAKE_XCRUN_LOG:?}"
  fi
  if [ "$skip" = "1" ]; then
    printf 'skip-build\n' >>"${FAKE_XCRUN_LOG:?}"
  else
    printf 'rebuild\n' >>"${FAKE_XCRUN_LOG:?}"
  fi
fi
exit 0
SH
chmod +x "$ROOT/bin/xcrun"

export PATH="$ROOT/bin:$PATH"
export OMI_SWIFT_TEST_DISCOVERY_ROOT="$ROOT/tests"
export OMI_SWIFT_TEST_PACKAGE_PATH="$ROOT/package"
export OMI_SWIFT_TEST_SUITE_WORKERS=2
export OMI_SWIFT_TEST_SERIAL_SUITES="AlphaTests"
export OMI_SWIFT_TEST_SUITE_BATCH_SIZE=1
export OMI_SWIFT_TEST_PREBUILD=1

export FAKE_XCRUN_LOG="$ROOT/same.log"
: >"$FAKE_XCRUN_LOG"
if ! OMI_SWIFT_TEST_SHARD_DIR="$ROOT/same-shards" "$RUNNER" >"$ROOT/same.out" 2>"$ROOT/same.err"; then
  cat "$ROOT/same.err" >&2
  fail "same-volume runner failed"
fi
grep -qx 'marker' "$FAKE_XCRUN_LOG" || fail "same-volume shard did not receive the cloned marker"
grep -qx 'skip-build' "$FAKE_XCRUN_LOG" || fail "same-volume shard did not skip the build"
find "$ROOT/same-shards" -mindepth 1 -maxdepth 1 | grep -q . && fail "same-volume run directory was left behind"
grep -q 'WARNING:' "$ROOT/same.err" && fail "same-volume run warned"

export FAKE_XCRUN_LOG="$ROOT/cross.log"
: >"$FAKE_XCRUN_LOG"
if ! OMI_SWIFT_TEST_SHARD_DIR="$DATA/shards" "$RUNNER" >"$ROOT/cross.out" 2>"$ROOT/cross.err"; then
  cat "$ROOT/cross.err" >&2
  fail "cross-volume runner failed"
fi
grep -q 'WARNING:' "$ROOT/cross.err" || fail "cross-volume run did not warn"
grep -qx 'no-marker' "$FAKE_XCRUN_LOG" || fail "cross-volume run copied the prebuilt scratch"
grep -qx 'rebuild' "$FAKE_XCRUN_LOG" || fail "cross-volume run did not fall back to a build"
grep -qx 'marker' "$FAKE_XCRUN_LOG" && fail "cross-volume log recorded a cloned marker"
if find "$DATA/shards" -name 'marker.txt' | grep -q .; then
  fail "cross-volume shard directory contains the prebuilt marker"
fi
find "$DATA/shards" -mindepth 1 -maxdepth 1 | grep -q . && fail "cross-volume run directory was left behind"

# Several worker and serial shards on the source volume, then cleanup.
mkdir -p "$ROOT/tests"
cat >"$ROOT/tests/BetaTests.swift" <<'SWIFT'
import XCTest
final class BetaTests: XCTestCase {
    func testOne() {}
}
SWIFT
export OMI_SWIFT_TEST_SERIAL_SUITES="AlphaTests"
export OMI_SWIFT_TEST_SUITE_WORKERS=2
export FAKE_XCRUN_LOG="$ROOT/multi.log"
: >"$FAKE_XCRUN_LOG"
if ! OMI_SWIFT_TEST_SHARD_DIR="$ROOT/same-shards" "$RUNNER" >"$ROOT/multi.out" 2>"$ROOT/multi.err"; then
  cat "$ROOT/multi.err" >&2
  fail "multi-shard runner failed"
fi
marker_count="$(grep -cx 'marker' "$FAKE_XCRUN_LOG" || true)"
[ "$marker_count" -ge 2 ] || fail "expected worker and serial clones, saw $marker_count"
find "$ROOT/same-shards" -mindepth 1 -maxdepth 1 | grep -q . && fail "multi-shard run directory was left behind"

echo "swift test shard volume tests passed"
