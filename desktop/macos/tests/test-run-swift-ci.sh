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

TMPDIR="$(mktemp -d)"
cleanup() {
  rm -rf "$TMPDIR"
}
trap cleanup EXIT

# The runner resolves the pin file relative to its own location
# (../ci/xcode-pin.json), so the sandbox mirrors that layout.
mkdir -p "$TMPDIR/macos/scripts" "$TMPDIR/macos/ci" "$TMPDIR/$PIN_APP_NAME/Contents/Developer/usr/bin" "$TMPDIR/bin"
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
export OMI_SWIFT_CI_XCODE_APP="$TMPDIR/$PIN_APP_NAME"
export FAKE_XCRUN_LOG="$TMPDIR/xcrun.log"
export FAKE_SUITE_LOG="$TMPDIR/suite.log"
export GITHUB_ENV="$TMPDIR/github-env"

"$TMPDIR/macos/scripts/run-swift-ci.sh" --select-toolchain
if ! grep -qx "DEVELOPER_DIR=$TMPDIR/$PIN_APP_NAME/Contents/Developer" "$GITHUB_ENV"; then
  fail "toolchain selection did not export DEVELOPER_DIR for subsequent CI steps"
fi

"$TMPDIR/macos/scripts/run-swift-ci.sh" --test
if ! grep -qx "$TMPDIR/$PIN_APP_NAME/Contents/Developer|4" "$FAKE_SUITE_LOG"; then
  fail "Swift suite did not inherit the selected toolchain and four worker default"
fi

"$TMPDIR/macos/scripts/run-swift-ci.sh" --release-compile
if ! grep -q -- 'swift build -c release --package-path Desktop --triple arm64-apple-macosx' "$FAKE_XCRUN_LOG"; then
  fail "release compile did not use the CI release command"
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

echo "run-swift-ci tests passed (pin $PIN_VERSION/$PIN_BUILD)"
