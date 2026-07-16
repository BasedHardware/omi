#!/usr/bin/env bash
# Pinned SwiftLint bootstrap and lint runner (#9843 Ticket 06).
#
# The SwiftPM build-tool plugin cannot run in release builds because SwiftPM
# rejects prebuild commands whose executable is itself source-built. This
# wrapper makes the same exact SwiftLint source available as an explicit macOS
# manifest check, with provenance and cache identity verified before linting.
set -euo pipefail

SWIFTLINT_VERSION="0.65.0"
SWIFTLINT_COMMIT="fd768ba9a0e8a4f96d550d98de6c4cf2af565cf1"
SWIFTLINT_REPO="https://github.com/realm/SwiftLint.git"

CACHE_DIR="${SWIFTLINT_CACHE_DIR:-${HOME}/.cache/omi-swiftlint}"
COMMIT12="${SWIFTLINT_COMMIT:0:12}"
BUILD_DIR="${CACHE_DIR}/${SWIFTLINT_VERSION}-${COMMIT12}"
BINARY="${BUILD_DIR}/.build/release/swiftlint"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DESKTOP_DIR="$MACOS_DIR/Desktop"
CONFIG_FILE="$DESKTOP_DIR/.swiftlint.yml"

die() { echo "FATAL(swiftlint-wrapper): $*" >&2; exit 1; }

bootstrap() {
  if [ -x "$BINARY" ]; then
    local cached_version
    cached_version="$("$BINARY" version 2>&1 | sed -n '1p')"
    if [ "$cached_version" = "$SWIFTLINT_VERSION" ]; then
      echo "swiftlint cache HIT: ${SWIFTLINT_VERSION} (${COMMIT12})" >&2
      return 0
    fi
    echo "swiftlint cache stale (got '${cached_version}'), rebuilding..." >&2
  fi

  command -v xcrun >/dev/null 2>&1 || die "xcrun not found — run on macOS with Xcode installed"
  rm -rf "$BUILD_DIR"
  mkdir -p "$(dirname "$BUILD_DIR")"
  echo "Bootstrapping SwiftLint ${SWIFTLINT_VERSION} from source..." >&2
  git clone --quiet --depth 1 --branch "$SWIFTLINT_VERSION" "$SWIFTLINT_REPO" "$BUILD_DIR"

  local actual_commit
  actual_commit="$(cd "$BUILD_DIR" && git rev-parse HEAD)"
  if [ "$actual_commit" != "$SWIFTLINT_COMMIT" ]; then
    die "commit mismatch: expected ${SWIFTLINT_COMMIT}, got ${actual_commit}"
  fi

  (
    cd "$BUILD_DIR"
    xcrun swift build -c release --product swiftlint
  )
  [ -x "$BINARY" ] || die "build completed but binary not found at ${BINARY}"

  local built_version
  built_version="$("$BINARY" version 2>&1 | sed -n '1p')"
  if [ "$built_version" != "$SWIFTLINT_VERSION" ]; then
    die "version mismatch: expected '${SWIFTLINT_VERSION}', got '${built_version}'"
  fi
}

case "${1:-}" in
  bootstrap)
    bootstrap
    ;;
  version)
    bootstrap >&2
    "$BINARY" version
    ;;
  digest)
    echo "$SWIFTLINT_COMMIT"
    ;;
  lint)
    shift
    bootstrap >&2
    cd "$DESKTOP_DIR"
    exec "$BINARY" lint --strict --config "$CONFIG_FILE" "$@"
    ;;
  *)
    die "usage: $0 {bootstrap|version|digest|lint}"
    ;;
esac
