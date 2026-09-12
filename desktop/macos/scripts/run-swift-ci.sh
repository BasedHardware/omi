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
    # No `rm -rf Desktop/.build`: a leftover local tree keeps incremental
    # state, and hosted runners start clean anyway. CI does NOT cache the
    # release build products: whole-module optimization recompiles on any
    # source change, so the measured compile time was 23-25 min with or
    # without a restored archive, while each 5.3 GB save evicted the small
    # tool caches from the repository's cache budget.
    # The regression mode below can only reuse this build when it carries
    # testability: `swift test -c release` needs `-enable-testing` for
    # `@testable import`, a plain release build does not have it, and that
    # flag difference invalidates the whole module graph — so without this the
    # regression step silently recompiles Omi_Computer and every dependency a
    # second time, ~28 min on top of this step's ~31. Measured locally: with
    # the flags, `swift test --skip-build` runs the suite in 6.9s.
    #
    # Only when the regression will actually run, because every other trigger
    # for this job (main pushes, scheduled health, Package.swift PRs) would
    # otherwise pay to compile test targets nothing executes.
    #
    # Bash 3.2 is the system bash on hosted runners and treats "${empty[@]}"
    # as unbound under `set -u`, so the array is only expanded when non-empty.
    release_build_args=()
    if [ "${OMI_SWIFT_RELEASE_BUILD_TESTS:-}" = "true" ]; then
      release_build_args=(--build-tests -Xswiftc -enable-testing)
    fi
    if [ "${#release_build_args[@]}" -gt 0 ]; then
      xcrun swift build -c release "${release_build_args[@]}" \
        --package-path Desktop --triple arm64-apple-macosx
    else
      xcrun swift build -c release --package-path Desktop --triple arm64-apple-macosx
    fi
    ;;
  --release-notification-regression)
    [ "$#" -eq 1 ] || usage
    select_toolchain
    cd "$MACOS_DIR"
    # Keep this narrow enough for a PR boundary check while exercising the
    # release compiler mode used for signed candidates. This is the direct
    # UserNotifications private-callback-to-MainActor regression suite.
    #
    # --skip-build when --release-compile already produced testable release
    # products; otherwise (a local invocation of this mode on its own) build
    # them here, which is the old behaviour.
    if [ "${OMI_SWIFT_RELEASE_BUILD_TESTS:-}" = "true" ]; then
      xcrun swift test -c release --skip-build \
        --package-path Desktop --filter UserNotificationCallbackBridgeTests/
    else
      xcrun swift test -c release --package-path Desktop --filter UserNotificationCallbackBridgeTests/
    fi
    ;;
  *)
    usage
    ;;
esac
