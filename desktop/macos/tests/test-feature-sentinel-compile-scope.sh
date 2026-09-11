#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_SCRIPT="$SCRIPT_DIR/test-feature-sentinel-negative-control.sh"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/omi-feature-sentinel-scope.XXXXXX")"

cleanup() {
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

MACOS_FIXTURE="$TMP_ROOT/macos"
mkdir -p \
  "$MACOS_FIXTURE/tests" \
  "$MACOS_FIXTURE/Desktop/Tests/SemanticFeatureSentinels" \
  "$TMP_ROOT/bin"
cp "$SOURCE_SCRIPT" "$MACOS_FIXTURE/tests/"

cat > "$MACOS_FIXTURE/Desktop/Package.swift" <<'SWIFT'
// swift-tools-version: 6.0
import PackageDescription
let package = Package(
  name: "Fixture",
  targets: [
    .target(
      name: "SemanticFeatureSentinels",
      path: "Tests/SemanticFeatureSentinels"
    ),
  ],
  swiftLanguageModes: [.v6]
)
SWIFT

cat > "$MACOS_FIXTURE/Desktop/Tests/SemanticFeatureSentinels/BareSlashRegexSentinelTests.swift" <<'SWIFT'
func sentinel() { _ = /\d+/ }
SWIFT
cat > "$MACOS_FIXTURE/Desktop/Tests/SemanticFeatureSentinels/StrictConcurrencySentinelTests.swift" <<'SWIFT'
func strictConcurrencySentinel() {}
SWIFT

cat > "$TMP_ROOT/bin/xcrun" <<'BASH'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$FAKE_XCRUN_LOG"

if [[ " $* " == *" --target SemanticFeatureSentinels "* ]]; then
  echo "Build of target 'SemanticFeatureSentinels' complete!"
  exit 0
fi

PACKAGE_PATH=""
while [[ "$#" -gt 0 ]]; do
  if [[ "$1" == "--package-path" ]]; then
    PACKAGE_PATH="$2"
    break
  fi
  shift
done

if grep -q 'ThisFeatureDoesNotExist12345' "$PACKAGE_PATH/Package.swift"; then
  echo "Build complete!"
  exit 0
fi

echo "error: var 'counter' is not concurrency-safe because it is nonisolated global shared mutable state" >&2
exit 1
BASH
chmod +x "$TMP_ROOT/bin/xcrun"

OUTPUT="$TMP_ROOT/output.txt"
FAKE_XCRUN_LOG="$TMP_ROOT/xcrun.log" \
  PATH="$TMP_ROOT/bin:$PATH" \
  bash "$MACOS_FIXTURE/tests/test-feature-sentinel-negative-control.sh" > "$OUTPUT"

grep -q '4 passed, 0 failed' "$OUTPUT"
grep -q -- '--target SemanticFeatureSentinels' "$TMP_ROOT/xcrun.log"
if grep -q -- '--build-tests' "$TMP_ROOT/xcrun.log"; then
  echo "feature sentinel invoked a package-wide test build" >&2
  exit 1
fi

TARGET_BUILD_COUNT="$(grep -c -- '--target SemanticFeatureSentinels' "$TMP_ROOT/xcrun.log" || true)"
test "$TARGET_BUILD_COUNT" = "1"

echo "feature sentinel compile scope test passed"
