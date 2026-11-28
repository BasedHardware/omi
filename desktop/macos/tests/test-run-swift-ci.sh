#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
RUNNER="$MACOS_DIR/scripts/run-swift-ci.sh"
PIN_FILE="$MACOS_DIR/ci/xcode-pin.json"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

if [ ! -f "$PIN_FILE" ]; then
  fail "missing Xcode pin file: $PIN_FILE"
fi

PIN_VERSION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' "$PIN_FILE")"
PIN_BUILD="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["build"])' "$PIN_FILE")"
PIN_APP_NAME="Xcode_${PIN_VERSION}.app"

# Strip a trailing slash: GitHub's macOS runners export TMPDIR with one, and BSD
# mktemp echoes the resulting "//" back while $PWD normalizes it, so the
# purchase-exposure path assertion below would never match.
TMP_ROOT="${TMPDIR:-/tmp}"
TMP_ROOT="${TMP_ROOT%/}"
TMPDIR="$(mktemp -d "$TMP_ROOT/omi-swift-ci-test.XXXXXX")"
cleanup() {
  rm -rf "$TMPDIR"
}
trap cleanup EXIT

# The runner resolves the pin file relative to its own location
# (../ci/xcode-pin.json), so the sandbox mirrors that layout.
mkdir -p "$TMPDIR/macos/scripts" "$TMPDIR/macos/ci" "$TMPDIR/macos/tests/purchase-exposure" "$TMPDIR/$PIN_APP_NAME/Contents/Developer/usr/bin" "$TMPDIR/bin"
cp "$RUNNER" "$TMPDIR/macos/scripts/run-swift-ci.sh"
chmod +x "$TMPDIR/macos/scripts/run-swift-ci.sh"
cp "$PIN_FILE" "$TMPDIR/macos/ci/xcode-pin.json"

cat >"$TMPDIR/$PIN_APP_NAME/Contents/Developer/usr/bin/xcodebuild" <<SH
#!/usr/bin/env bash
set -euo pipefail
echo "Xcode \${FAKE_XCODE_VERSION:-$PIN_VERSION}"
echo "Build version \${FAKE_XCODE_BUILD:-$PIN_BUILD}"
SH
chmod +x "$TMPDIR/$PIN_APP_NAME/Contents/Developer/usr/bin/xcodebuild"

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
  expected="swift test -c release --package-path Desktop --triple arm64-apple-macosx -Xswiftc -emit-const-values -Xswiftc -enable-testing --skip-build --filter UserNotificationCallbackBridgeTests/"
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

# This fixture tests runner orchestration with fake toolchain/test boundaries.
# Ordinary CI still executes the real purchase-exposure harness through --test.
cat >"$TMPDIR/macos/tests/purchase-exposure/run.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
printf '%s|%s|%s\n' "$PWD" "$DEVELOPER_DIR" "$*" >> "$FAKE_PURCHASE_LOG"
exit "${FAKE_PURCHASE_FAILURE:-0}"
SH

export PATH="$TMPDIR/bin:$PATH"
export OMI_SWIFT_CI_XCODE_APP="$TMPDIR/$PIN_APP_NAME"
export FAKE_XCRUN_LOG="$TMPDIR/xcrun.log"
export FAKE_RELEASE_BUILD="$TMPDIR/release-build"
export FAKE_SUITE_LOG="$TMPDIR/suite.log"
export FAKE_PURCHASE_LOG="$TMPDIR/purchase-exposure.log"
export GITHUB_ENV="$TMPDIR/github-env"

"$TMPDIR/macos/scripts/run-swift-ci.sh" --select-toolchain
if ! grep -qx "DEVELOPER_DIR=$TMPDIR/$PIN_APP_NAME/Contents/Developer" "$GITHUB_ENV"; then
  fail "toolchain selection did not export DEVELOPER_DIR for subsequent CI steps"
fi
if [ -s "$FAKE_PURCHASE_LOG" ]; then
  fail "toolchain-only mode must not execute purchase-exposure tests"
fi

"$TMPDIR/macos/scripts/run-swift-ci.sh" --test
if ! grep -qx "$TMPDIR/$PIN_APP_NAME/Contents/Developer|4" "$FAKE_SUITE_LOG"; then
  fail "Swift suite did not inherit the selected toolchain and four worker default"
fi
if [ "$(wc -l < "$FAKE_PURCHASE_LOG" | tr -d ' ')" -ne 1 ] ||
  ! grep -Fqx "$TMPDIR/macos|$TMPDIR/$PIN_APP_NAME/Contents/Developer|" "$FAKE_PURCHASE_LOG"; then
  fail "test mode must run purchase-exposure once, without arguments, in the selected macOS toolchain"
fi

# A failing required subharness must fail --test before the broader Swift suites.
: > "$FAKE_PURCHASE_LOG"
: > "$FAKE_SUITE_LOG"
: > "$FAKE_XCRUN_LOG"
purchase_status=0
FAKE_PURCHASE_FAILURE=37 "$TMPDIR/macos/scripts/run-swift-ci.sh" --test >"$TMPDIR/purchase-failure.out" 2>&1 || purchase_status=$?
if [ "$purchase_status" -ne 37 ] || [ "$(wc -l < "$FAKE_PURCHASE_LOG" | tr -d ' ')" -ne 1 ]; then
  fail "runner did not propagate the invoked purchase-exposure harness failure (expected 37, got $purchase_status)"
fi
if [ -s "$FAKE_SUITE_LOG" ] || grep -Eq 'swift (build|test) ' "$FAKE_XCRUN_LOG"; then
  fail "runner continued Swift build/test execution after purchase-exposure failed"
fi
echo "purchase-exposure invocation and failure propagation passed (exit $purchase_status; no later Swift suites)"
: > "$FAKE_PURCHASE_LOG"

# Generated-only PRs compile both targets in one debug build and execute no suites.
: > "$FAKE_XCRUN_LOG"
: > "$FAKE_SUITE_LOG"
"$TMPDIR/macos/scripts/run-swift-ci.sh" --test-compile
if ! grep -qx 'swift build -c debug --package-path Desktop --build-tests' "$FAKE_RELEASE_BUILD"; then
  fail "debug app and test targets must compile together"
fi
if [ "$(grep -c 'swift build ' "$FAKE_XCRUN_LOG")" -ne 1 ] || grep -q 'swift test ' "$FAKE_XCRUN_LOG" || [ -s "$FAKE_SUITE_LOG" ] || [ -s "$FAKE_PURCHASE_LOG" ]; then
  fail "compile-only mode must invoke one build and no test execution"
fi
if FAKE_BUILD_FAILURE=1 "$TMPDIR/macos/scripts/run-swift-ci.sh" --test-compile; then
  fail "runner hid a debug test compilation failure"
fi
if "$TMPDIR/macos/scripts/run-swift-ci.sh" --test-compile --unexpected; then
  fail "runner accepted unrecognized debug compile options"
fi
rm "$FAKE_RELEASE_BUILD"

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
if ! grep -qx 'swift build -c release --package-path Desktop --triple arm64-apple-macosx -Xswiftc -emit-const-values -Xswiftc -enable-testing --build-tests' "$FAKE_RELEASE_BUILD"; then
  fail "release app and test targets must build together with the stable runner's default concurrency"
fi
if ! grep -q -- 'swift test -c release --package-path Desktop --triple arm64-apple-macosx -Xswiftc -emit-const-values -Xswiftc -enable-testing --skip-build --filter UserNotificationCallbackBridgeTests/' "$FAKE_XCRUN_LOG"; then
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
if ! grep -q "expected Xcode $PIN_VERSION" "$TMPDIR/wrong-version.out"; then
  fail "wrong Xcode version did not produce an actionable error naming the pinned version"
fi

if FAKE_XCODE_BUILD=ZZZ999 "$TMPDIR/macos/scripts/run-swift-ci.sh" --select-toolchain >"$TMPDIR/wrong-build.out" 2>&1; then
  fail "runner accepted an Xcode build other than the pinned CI build"
fi
if ! grep -q "expected Xcode build $PIN_BUILD" "$TMPDIR/wrong-build.out"; then
  fail "wrong Xcode build did not produce an actionable error naming the pinned build"
fi

# The pin file is the single source of truth: removing it from the sandbox
# layout must fail closed instead of falling back to any default toolchain.
PIN_BACKUP="$TMPDIR/pin-backup.json"
mv "$TMPDIR/macos/ci/xcode-pin.json" "$PIN_BACKUP"
if "$TMPDIR/macos/scripts/run-swift-ci.sh" --select-toolchain >"$TMPDIR/missing-pin.out" 2>&1; then
  fail "runner kept working without the pin file"
fi
if ! grep -q 'missing Xcode pin file' "$TMPDIR/missing-pin.out"; then
  fail "a missing pin file did not produce an actionable error"
fi
mv "$PIN_BACKUP" "$TMPDIR/macos/ci/xcode-pin.json"

if [ -s "$FAKE_PURCHASE_LOG" ]; then
  fail "compile, release-regression and toolchain-only modes must not execute purchase-exposure tests"
fi

echo "run-swift-ci tests passed (pin $PIN_VERSION/$PIN_BUILD)"
