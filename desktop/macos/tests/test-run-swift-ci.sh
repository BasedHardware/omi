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
elif [ "${2:-}" = build ]; then
  [ "${FAKE_BUILD_FAILURE:-0}" = 0 ] || exit 19
  if [[ " $* " == *" --build-tests "* ]]; then
    printf '%s\n' "$*" > "$FAKE_RELEASE_BUILD"
  fi
elif [ "${2:-}" = test ]; then
  [ -f "$FAKE_RELEASE_BUILD" ] || exit 20
  expected="swift test -c release --package-path Desktop --triple arm64-apple-macosx -Xswiftc -enable-testing --skip-build --filter UserNotificationCallbackBridgeTests/"
  [ "$*" = "$expected" ] || exit 21
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
export FAKE_RELEASE_BUILD="$TMPDIR/release-build"
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

# Running the regression without compiled tests must fail, never build implicitly.
if "$TMPDIR/macos/scripts/run-swift-ci.sh" --release-notification-regression; then
  fail "release regression accepted a missing test build"
fi
: > "$FAKE_XCRUN_LOG"
"$TMPDIR/macos/scripts/run-swift-ci.sh" --release-test-compile
"$TMPDIR/macos/scripts/run-swift-ci.sh" --release-notification-regression
if [ "$(grep -c 'swift build ' "$FAKE_XCRUN_LOG")" -ne 1 ]; then
  fail "release test compile and regression must invoke exactly one build"
fi
if ! grep -qx 'swift build -c release --package-path Desktop --triple arm64-apple-macosx -Xswiftc -enable-testing --build-tests' "$FAKE_RELEASE_BUILD"; then
  fail "release app and test targets must build together with the same destination"
fi
if ! grep -q -- 'swift test -c release --package-path Desktop --triple arm64-apple-macosx -Xswiftc -enable-testing --skip-build --filter UserNotificationCallbackBridgeTests/' "$FAKE_XCRUN_LOG"; then
  fail "release notification regression did not reuse the compiled tests"
fi
if FAKE_BUILD_FAILURE=1 "$TMPDIR/macos/scripts/run-swift-ci.sh" --release-test-compile; then
  fail "runner hid a release test compilation failure"
fi
if "$TMPDIR/macos/scripts/run-swift-ci.sh" --release-test-compile --unexpected; then
  fail "runner accepted unrecognized release compile options"
fi

if FAKE_XCODE_VERSION=16.5 "$TMPDIR/macos/scripts/run-swift-ci.sh" --select-toolchain >"$TMPDIR/wrong-version.out" 2>&1; then
  fail "runner accepted an Xcode version other than the pinned CI version"
fi
if ! grep -q 'expected Xcode 16.4' "$TMPDIR/wrong-version.out"; then
  fail "wrong Xcode version did not produce an actionable error"
fi

echo "run-swift-ci tests passed"
