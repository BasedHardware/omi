#!/usr/bin/env bash
# Feature sentinel tests (#9843 Ticket 09).
#
# Two controls:
# 1. POSITIVE: the SemanticFeatureSentinels target build produces a non-Sendable
#    capture warning, proving -strict-concurrency=complete is active. If the
#    flag is removed from Package.swift, the warning disappears and this test
#    fails — catching the "fake strictness" trap.
# 2. NEGATIVE: SwiftPM silently accepts a fake upcoming-feature name, proving
#    why feature verification is needed.
set -euo pipefail

if ! command -v xcrun >/dev/null 2>&1; then
  echo "skip: requires macOS with Xcode"
  exit 0
fi

PASS=0
FAIL=0
ok() { echo "  ok: $1"; PASS=$((PASS + 1)); }
nok() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "== feature sentinel tests"

# --- POSITIVE: strict-concurrency=complete produces a non-Sendable warning ---
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SENTINEL="$MACOS_DIR/Desktop/Tests/SemanticFeatureSentinels/StrictConcurrencySentinelTests.swift"

# Force recompilation to surface the warning
touch "$SENTINEL"
BUILD_OUTPUT=$(xcrun swift build --package-path "$MACOS_DIR/Desktop" --target SemanticFeatureSentinels 2>&1)

if echo "$BUILD_OUTPUT" | grep -qi "non-Sendable\|non-sendable\|data race"; then
  ok "strict-concurrency=complete is active (non-Sendable warning produced)"
else
  nok "strict-concurrency=complete flag appears inactive (no non-Sendable warning in build output)"
fi

if echo "$BUILD_OUTPUT" | grep -qi "Build of target.*complete\|Build complete"; then
  ok "BareSlashRegexLiterals is active (sentinel target compiles)"
else
  nok "sentinel target build failed"
fi

# --- NEGATIVE: SwiftPM silently accepts unknown feature names ---
TMPDIR_FEAT=$(mktemp -d)
trap 'rm -rf "$TMPDIR_FEAT"' EXIT

mkdir -p "$TMPDIR_FEAT/Sources/MyLib"
cat > "$TMPDIR_FEAT/Package.swift" << 'SWIFT'
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
echo 'public func hello() {}' > "$TMPDIR_FEAT/Sources/MyLib/hello.swift"

if xcrun swift build --package-path "$TMPDIR_FEAT" 2>/dev/null; then
  ok "SwiftPM accepts unknown upcoming-feature name without error (the silent-acceptance trap)"
else
  nok "SwiftPM rejected unknown feature (unexpected)"
fi

echo "== ${PASS} passed, ${FAIL} failed"
[ "$FAIL" -eq 0 ] || exit 1
