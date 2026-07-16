#!/usr/bin/env bash
# Feature sentinel tests (#9843 Ticket 09).
#
# Three controls (updated for the Swift 6 language-mode cutover):
# 1. POSITIVE (mode): the package declares `swiftLanguageModes: [.v6]`. Swift 6
#    enforces strict concurrency inherently — there is no flag to silently
#    remove — so verifying the declared mode is the durable guard.
# 2. POSITIVE (compile + upcoming feature): the SemanticFeatureSentinels target
#    builds, proving BareSlashRegexLiterals is active and the target compiles
#    under Swift 6 strict concurrency.
# 3. POSITIVE (rejection): a deliberately unsafe non-Sendable `Task.detached`
#    capture is *rejected* by the compiler under Swift 6 — the direct proof that
#    strict concurrency is enforced (it was a warning under Swift 5 +
#    `-strict-concurrency=complete`).
# 4. NEGATIVE: SwiftPM silently accepts a fake upcoming-feature name, proving
#    why feature verification is needed.
set -euo pipefail

if ! command -v xcrun >/dev/null 2>&1; then
  echo "skip: requires macOS with Xcode"
  exit 0
fi

PASS=0
FAIL=0
TMPDIRS=()
cleanup() {
  for dir in "${TMPDIRS[@]}"; do
    rm -rf "$dir"
  done
}
trap cleanup EXIT
ok() { echo "  ok: $1"; PASS=$((PASS + 1)); }
nok() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "== feature sentinel tests"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MANIFEST="$MACOS_DIR/Desktop/Package.swift"
SENTINEL="$MACOS_DIR/Desktop/Tests/SemanticFeatureSentinels/StrictConcurrencySentinelTests.swift"

# --- POSITIVE (mode): package declares Swift 6 language mode ---
if grep -q 'swiftLanguageModes: \[.v6\]' "$MANIFEST"; then
  ok "package declares swiftLanguageModes: [.v6] (strict concurrency is inherent)"
else
  nok "package does not declare swiftLanguageModes: [.v6]"
fi

# --- POSITIVE (compile + upcoming feature): sentinel target builds under Swift 6 ---
# Force recompilation so the result reflects the current source even when the
# caller has already warmed the package build cache.
touch "$SENTINEL"
rm -rf \
  "$MACOS_DIR/Desktop/.build/debug/SemanticFeatureSentinels.build" \
  "$MACOS_DIR/Desktop/.build/arm64-apple-macosx/debug/SemanticFeatureSentinels.build"
if BUILD_OUTPUT=$(xcrun swift build --package-path "$MACOS_DIR/Desktop" --target SemanticFeatureSentinels 2>&1); then
  BUILD_STATUS=0
else
  BUILD_STATUS=$?
fi

if [[ "$BUILD_STATUS" -eq 0 ]] && echo "$BUILD_OUTPUT" | grep -qi "Build of target.*complete\|Build complete"; then
  ok "BareSlashRegexLiterals is active and sentinel target compiles under Swift 6"
else
  nok "sentinel target build failed"
  echo "$BUILD_OUTPUT" | tail -80
fi

# --- POSITIVE (rejection): Swift 6 rejects non-isolated global mutable state ---
# Under Swift 5 this was a downgradeable warning; under Swift 6 strict
# concurrency it is a hard compile error. A self-contained Swift 6 package with
# non-isolated global shared mutable state must fail to build.
TMPDIR_SENTINEL=$(mktemp -d)
TMPDIRS+=("$TMPDIR_SENTINEL")
mkdir -p "$TMPDIR_SENTINEL/Sources/Sentinel"
cat > "$TMPDIR_SENTINEL/Package.swift" << 'SWIFT'
// swift-tools-version: 6.0
import PackageDescription
let package = Package(
  name: "Sentinel",
  targets: [
    .target(name: "Sentinel", path: "Sources/Sentinel"),
  ],
  swiftLanguageModes: [.v6]
)
SWIFT
cat > "$TMPDIR_SENTINEL/Sources/Sentinel/sentinel.swift" << 'SWIFT'
var counter = 0
func trigger() { counter += 1 }
SWIFT
SENTINEL_BUILD_OUTPUT=$(xcrun swift build --package-path "$TMPDIR_SENTINEL" 2>&1) || true
if echo "$SENTINEL_BUILD_OUTPUT" | grep -qi "concurrency-safe\|data race\|non-Sendable\|non-sendable" \
  && ! xcrun swift build --package-path "$TMPDIR_SENTINEL" >/dev/null 2>&1; then
  ok "Swift 6 rejects non-isolated global mutable state (strict concurrency enforced)"
else
  nok "Swift 6 did not reject non-isolated global mutable state (strict concurrency inactive)"
  echo "$SENTINEL_BUILD_OUTPUT" | tail -40
fi

# --- NEGATIVE: SwiftPM silently accepts unknown feature names ---
TMPDIR_FEAT=$(mktemp -d)
TMPDIRS+=("$TMPDIR_FEAT")

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
