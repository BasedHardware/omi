#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="$SCRIPT_DIR/../scripts/run-swift-ci.sh"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

TMPDIR="$(mktemp -d)"
cleanup() {
  rm -rf "$TMPDIR"
}
trap cleanup EXIT

mkdir -p "$TMPDIR/macos/scripts" "$TMPDIR/Xcode_16.4.app/Contents/Developer/usr/bin" "$TMPDIR/bin"
cp "$RUNNER" "$TMPDIR/macos/scripts/run-swift-ci.sh"
chmod +x "$TMPDIR/macos/scripts/run-swift-ci.sh"

cat >"$TMPDIR/Xcode_16.4.app/Contents/Developer/usr/bin/xcodebuild" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
echo "Xcode ${FAKE_XCODE_VERSION:-16.4}"
echo "Build version ${FAKE_XCODE_BUILD:-16F6}"
SH
chmod +x "$TMPDIR/Xcode_16.4.app/Contents/Developer/usr/bin/xcodebuild"

cat >"$TMPDIR/bin/xcrun" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
printf '%s|%s\n' "$DEVELOPER_DIR" "$*" >> "$FAKE_XCRUN_LOG"
if [ "${1:-}" = "swift" ] && [ "${2:-}" = "--version" ]; then
  echo "Swift version fake"
fi
SH
chmod +x "$TMPDIR/bin/xcrun"

cat >"$TMPDIR/macos/scripts/swift-test-suites.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
printf '%s|%s\n' "$DEVELOPER_DIR" "$OMI_SWIFT_TEST_SUITE_WORKERS" >> "$FAKE_SUITE_LOG"
SH
chmod +x "$TMPDIR/macos/scripts/swift-test-suites.sh"

export PATH="$TMPDIR/bin:$PATH"
export OMI_SWIFT_CI_XCODE_APP="$TMPDIR/Xcode_16.4.app"
export FAKE_XCRUN_LOG="$TMPDIR/xcrun.log"
export FAKE_SUITE_LOG="$TMPDIR/suite.log"
export GITHUB_ENV="$TMPDIR/github-env"

"$TMPDIR/macos/scripts/run-swift-ci.sh" --select-toolchain
if ! grep -qx "DEVELOPER_DIR=$TMPDIR/Xcode_16.4.app/Contents/Developer" "$GITHUB_ENV"; then
  fail "toolchain selection did not export DEVELOPER_DIR for subsequent CI steps"
fi

"$TMPDIR/macos/scripts/run-swift-ci.sh" --test
if ! grep -qx "$TMPDIR/Xcode_16.4.app/Contents/Developer|4" "$FAKE_SUITE_LOG"; then
  fail "Swift suite did not inherit the selected toolchain and four worker default"
fi

"$TMPDIR/macos/scripts/run-swift-ci.sh" --release-compile
if ! grep -q -- 'swift build -c release --package-path Desktop --triple arm64-apple-macosx' "$FAKE_XCRUN_LOG"; then
  fail "release compile did not use the CI release command"
fi

if FAKE_XCODE_VERSION=16.5 "$TMPDIR/macos/scripts/run-swift-ci.sh" --select-toolchain >"$TMPDIR/wrong-version.out" 2>&1; then
  fail "runner accepted an Xcode version other than the pinned CI version"
fi
if ! grep -q 'expected Xcode 16.4' "$TMPDIR/wrong-version.out"; then
  fail "wrong Xcode version did not produce an actionable error"
fi

echo "run-swift-ci tests passed"
