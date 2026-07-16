#!/usr/bin/env bash
# Negative control: proves SwiftPM silently accepts unknown upcoming-feature
# names (#9843 Ticket 09). This is the critical trap — "fake strictness is
# worse than none." A misspelled feature name compiles cleanly, giving false
# confidence that a safety feature is active when it is silently ignored.
#
# This test creates a minimal temp SwiftPM package with a deliberately fake
# feature name, builds it, and asserts the build succeeds — proving the
# compiler does not reject unknown features.
set -euo pipefail

if ! command -v xcrun >/dev/null 2>&1; then
  echo "skip: requires macOS with Xcode"
  exit 0
fi

PASS=0
FAIL=0
ok() { echo "  ok: $1"; PASS=$((PASS + 1)); }
nok() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "== semantic feature sentinel negative control"

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

# Create a minimal SwiftPM package with a FAKE feature name
mkdir -p "$TMPDIR/Sources/MyLib"
cat > "$TMPDIR/Package.swift" << 'SWIFT'
// swift-tools-version: 5.9
import PackageDescription
let package = Package(
  name: "FakeFeatureTest",
  targets: [
    .target(name: "MyLib", swiftSettings: [
      .enableUpcomingFeature("ThisFeatureDoesNotExist12345"),
    ]),
  ]
)
SWIFT

echo 'public func hello() {}' > "$TMPDIR/Sources/MyLib/hello.swift"

# Build — SwiftPM should ACCEPT the fake feature name without error
if xcrun swift build --package-path "$TMPDIR" 2>/dev/null; then
  ok "SwiftPM accepts unknown upcoming-feature name without error"
else
  nok "SwiftPM rejected unknown feature (unexpected — this means the trap is closed)"
fi

# Contrast: the REAL features used by the sentinel target DO take effect
# (verified by the SemanticFeatureSentinels target compiling with
# BareSlashRegexLiterals and -strict-concurrency=complete active).

echo "== ${PASS} passed, ${FAIL} failed"
[ "$FAIL" -eq 0 ] || exit 1
