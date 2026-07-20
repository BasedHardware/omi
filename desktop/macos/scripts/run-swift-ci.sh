#!/usr/bin/env bash
# Run the pinned desktop Swift CI contract locally or in GitHub Actions.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
EXPECTED_XCODE_VERSION="16.4"
EXPECTED_XCODE_BUILD="16F6"
XCODE_APP="${OMI_SWIFT_CI_XCODE_APP:-/Applications/Xcode_16.4.app}"

usage() {
  echo "usage: $0 --select-toolchain | --test | --release-compile | --release-notification-regression" >&2
  exit 2
}

select_toolchain() {
  if [ ! -d "$XCODE_APP" ]; then
    echo "FAIL: desktop Swift CI requires Xcode $EXPECTED_XCODE_VERSION at $XCODE_APP." >&2
    echo "Available Xcodes:" >&2
    ls -d /Applications/Xcode*.app 2>/dev/null >&2 || true
    exit 1
  fi

  DEVELOPER_DIR="$XCODE_APP/Contents/Developer"
  if [ ! -x "$DEVELOPER_DIR/usr/bin/xcodebuild" ]; then
    echo "FAIL: Xcode developer directory is incomplete: $DEVELOPER_DIR" >&2
    exit 1
  fi
  export DEVELOPER_DIR

  echo "=== xcodebuild -version ==="
  xcode_version="$("$DEVELOPER_DIR"/usr/bin/xcodebuild -version)"
  printf '%s\n' "$xcode_version"
  echo "=== xcrun swift --version ==="
  xcrun swift --version

  actual_version="$(printf '%s\n' "$xcode_version" | sed -n '1p')"
  actual_build="$(printf '%s\n' "$xcode_version" | sed -n '2p' | awk '{print $NF}')"
  if [ "$actual_version" != "Xcode $EXPECTED_XCODE_VERSION" ]; then
    echo "FAIL: expected Xcode $EXPECTED_XCODE_VERSION, got: $actual_version" >&2
    exit 1
  fi
  if [ "$actual_build" != "$EXPECTED_XCODE_BUILD" ]; then
    echo "FAIL: expected Xcode build $EXPECTED_XCODE_BUILD, got: $actual_build" >&2
    exit 1
  fi

  if [ -n "${GITHUB_ENV:-}" ]; then
    printf 'DEVELOPER_DIR=%s\n' "$DEVELOPER_DIR" >> "$GITHUB_ENV"
  fi
  echo "Pinned toolchain confirmed: $actual_version ($actual_build)"
}

case "${1:-}" in
  --select-toolchain)
    [ "$#" -eq 1 ] || usage
    select_toolchain
    ;;
  --test)
    [ "$#" -eq 1 ] || usage
    select_toolchain
    cd "$MACOS_DIR"
    OMI_SWIFT_TEST_SUITE_WORKERS="${OMI_SWIFT_TEST_SUITE_WORKERS:-4}" \
      "$SCRIPT_DIR/swift-test-suites.sh"
    ;;
  --release-compile)
    [ "$#" -eq 1 ] || usage
    select_toolchain
    cd "$MACOS_DIR"
    rm -rf Desktop/.build
    ./scripts/generate-desktop-core-bindings.sh
    xcrun swift build -c release --package-path Desktop --triple arm64-apple-macosx
    ;;
  --release-notification-regression)
    [ "$#" -eq 1 ] || usage
    select_toolchain
    cd "$MACOS_DIR"
    # Keep this narrow enough for a PR boundary check while exercising the
    # release compiler mode used for signed candidates. This is the direct
    # UserNotifications private-callback-to-MainActor regression suite.
    xcrun swift test -c release --package-path Desktop --filter UserNotificationCallbackBridgeTests/
    ;;
  *)
    usage
    ;;
esac
