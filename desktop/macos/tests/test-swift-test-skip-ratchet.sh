#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
RATCHET="$MACOS_DIR/scripts/swift-test-skip-ratchet.py"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

TMPDIR="$(mktemp -d)"
cleanup() {
  rm -rf "$TMPDIR"
}
trap cleanup EXIT

mkdir -p "$TMPDIR/tests"
cat >"$TMPDIR/tests/ExampleTests.swift" <<'SWIFT'
import XCTest
final class ExampleTests: XCTestCase {
    func testKnownRed() {}
}
SWIFT

cat >"$TMPDIR/ok.json" <<'JSON'
{
  "max_skip_count": 1,
  "allowed_tests": ["ExampleTests/testKnownRed"],
  "skips": [
    {
      "test": "ExampleTests/testKnownRed",
      "issue": "https://github.com/BasedHardware/omi/issues/1",
      "reason": "Fixture known-red test."
    }
  ]
}
JSON

if ! "$RATCHET" --check --skip-file "$TMPDIR/ok.json" --tests-root "$TMPDIR/tests" >"$TMPDIR/ok.out"; then
  fail "valid ratchet file failed"
fi
if ! grep -q "OK: Swift XCTest method skips at ratchet (1)." "$TMPDIR/ok.out"; then
  fail "valid ratchet output did not report the count"
fi

args="$("$RATCHET" --skip-file "$TMPDIR/ok.json" --args-for-suite ExampleTests)"
expected=$'--skip\nExampleTests/testKnownRed'
if [ "$args" != "$expected" ]; then
  fail "args-for-suite output was '$args'"
fi

cat >"$TMPDIR/too-many.json" <<'JSON'
{
  "max_skip_count": 0,
  "allowed_tests": ["ExampleTests/testKnownRed"],
  "skips": [
    {
      "test": "ExampleTests/testKnownRed",
      "issue": "https://github.com/BasedHardware/omi/issues/1",
      "reason": "Fixture known-red test."
    }
  ]
}
JSON
if "$RATCHET" --check --skip-file "$TMPDIR/too-many.json" --tests-root "$TMPDIR/tests" \
    >"$TMPDIR/too-many.out" 2>"$TMPDIR/too-many.err"; then
  fail "ratchet unexpectedly allowed a skip-count increase"
fi
if ! grep -q "skip count rose to 1 (max_skip_count 0)" "$TMPDIR/too-many.err"; then
  fail "ratchet failure did not explain the skip-count increase"
fi

cat >"$TMPDIR/stale.json" <<'JSON'
{
  "max_skip_count": 1,
  "allowed_tests": ["ExampleTests/testMissing"],
  "skips": [
    {
      "test": "ExampleTests/testMissing",
      "issue": "https://github.com/BasedHardware/omi/issues/1",
      "reason": "Fixture known-red test."
    }
  ]
}
JSON
if "$RATCHET" --check --skip-file "$TMPDIR/stale.json" --tests-root "$TMPDIR/tests" \
    >"$TMPDIR/stale.out" 2>"$TMPDIR/stale.err"; then
  fail "ratchet unexpectedly allowed a stale skipped method"
fi
if ! grep -q "skipped method no longer exists: ExampleTests/testMissing" "$TMPDIR/stale.err"; then
  fail "stale skip failure did not identify the missing method"
fi

cat >"$TMPDIR/tests/SwapTests.swift" <<'SWIFT'
import XCTest
final class SwapTests: XCTestCase {
    func testNewKnownRed() {}
}
SWIFT
cat >"$TMPDIR/swapped.json" <<'JSON'
{
  "max_skip_count": 1,
  "allowed_tests": ["ExampleTests/testKnownRed"],
  "skips": [
    {
      "test": "SwapTests/testNewKnownRed",
      "issue": "https://github.com/BasedHardware/omi/issues/2",
      "reason": "Fixture same-count swap."
    }
  ]
}
JSON
if "$RATCHET" --check --skip-file "$TMPDIR/swapped.json" --tests-root "$TMPDIR/tests" \
    >"$TMPDIR/swapped.out" 2>"$TMPDIR/swapped.err"; then
  fail "ratchet unexpectedly allowed a same-count skipped-test swap"
fi
if ! grep -q "new skipped test IDs are not in the ratcheted baseline: SwapTests/testNewKnownRed" \
    "$TMPDIR/swapped.err"; then
  fail "same-count swap failure did not identify the new skipped test"
fi

# --- slow-suite deferral list ---

cat >"$TMPDIR/tests/SlowHarnessTests.swift" <<'SWIFT'
import XCTest
final class SlowHarnessTests: XCTestCase {
    func testOne() {}
}
SWIFT
cat >"$TMPDIR/slow-ok.json" <<'JSON'
{
  "max_slow_suite_count": 1,
  "slow_suites": {
    "SlowHarnessTests": {
      "reason": "Fixture: measured slow performance harness.",
      "evidence": "hermetic fixture run 2026-09-08"
    }
  }
}
JSON
if ! "$RATCHET" --slow-check --slow-file "$TMPDIR/slow-ok.json" --tests-root "$TMPDIR/tests" \
    >"$TMPDIR/slow-ok.out"; then
  fail "valid slow-suite file failed"
fi
if ! grep -q "OK: slow-suite deferrals at ratchet (1)." "$TMPDIR/slow-ok.out"; then
  fail "valid slow-suite output did not report the count"
fi
slow_list="$("$RATCHET" --slow-list --slow-file "$TMPDIR/slow-ok.json")"
if [ "$slow_list" != "SlowHarnessTests" ]; then
  fail "slow-list output was '$slow_list'"
fi

cat >"$TMPDIR/slow-too-many.json" <<'JSON'
{
  "max_slow_suite_count": 0,
  "slow_suites": {
    "SlowHarnessTests": {
      "reason": "Fixture: measured slow performance harness.",
      "evidence": "hermetic fixture run 2026-09-08"
    }
  }
}
JSON
if "$RATCHET" --slow-check --slow-file "$TMPDIR/slow-too-many.json" --tests-root "$TMPDIR/tests" \
    >"$TMPDIR/slow-too-many.out" 2>"$TMPDIR/slow-too-many.err"; then
  fail "slow-suite ratchet unexpectedly allowed a count increase"
fi
if ! grep -q "slow-suite count rose to 1 (max_slow_suite_count 0)" "$TMPDIR/slow-too-many.err"; then
  fail "slow-suite ratchet failure did not explain the count increase"
fi

cat >"$TMPDIR/slow-stale.json" <<'JSON'
{
  "max_slow_suite_count": 1,
  "slow_suites": {
    "RetiredHarnessTests": {
      "reason": "Fixture: deferred suite no longer exists.",
      "evidence": "hermetic fixture run 2026-09-08"
    }
  }
}
JSON
if "$RATCHET" --slow-check --slow-file "$TMPDIR/slow-stale.json" --tests-root "$TMPDIR/tests" \
    >"$TMPDIR/slow-stale.out" 2>"$TMPDIR/slow-stale.err"; then
  fail "slow-suite ratchet unexpectedly allowed a nonexistent suite"
fi
if ! grep -q "deferred slow suite no longer exists: RetiredHarnessTests" "$TMPDIR/slow-stale.err"; then
  fail "stale slow-suite failure did not identify the missing suite"
fi

cat >"$TMPDIR/slow-unjustified.json" <<'JSON'
{
  "max_slow_suite_count": 1,
  "slow_suites": {
    "SlowHarnessTests": {
      "reason": "Fixture: measured slow performance harness.",
      "evidence": ""
    }
  }
}
JSON
if "$RATCHET" --slow-check --slow-file "$TMPDIR/slow-unjustified.json" --tests-root "$TMPDIR/tests" \
    >"$TMPDIR/slow-unjustified.out" 2>"$TMPDIR/slow-unjustified.err"; then
  fail "slow-suite ratchet unexpectedly allowed an entry without evidence"
fi
if ! grep -q "slow_suites\[SlowHarnessTests\].evidence must be a non-empty string" "$TMPDIR/slow-unjustified.err"; then
  fail "unjustified slow-suite failure did not name the missing evidence"
fi

echo "swift-test-skip-ratchet tests passed"
