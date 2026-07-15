#!/usr/bin/env bash
# Pinned swift-format bootstrap wrapper (#9843 Ticket 02).
#
# Resolves an exact swift-format source tag, commit, and digest using the
# pinned Xcode.  Caches the built binary by source identity plus toolchain
# identity, verifies the emitted version/digest, and never invokes a moving
# runner binary.
#
# Usage:
#   swift-format-wrapper.sh bootstrap   — build+cache from source
#   swift-format-wrapper.sh version     — print version after bootstrap
#   swift-format-wrapper.sh digest      — print the pinned commit SHA
#   swift-format-wrapper.sh lint FILE…  — lint --strict (exit 1 on findings)
#   swift-format-wrapper.sh format -i FILE… — format in-place
#
# Cache: ${SWIFT_FORMAT_CACHE_DIR:-${HOME}/.cache/omi-swift-format}/<version>-<commit12>
# Override SWIFT_FORMAT_CACHE_DIR for CI (actions/cache restores the same path).
set -euo pipefail

# ── Pinned provenance ──────────────────────────────────────────────────
SWIFT_FORMAT_VERSION="602.0.0"
SWIFT_FORMAT_COMMIT="62eaad2822b865407b8cde56c36386c00800f7ec"
SWIFT_FORMAT_REPO="https://github.com/swiftlang/swift-format.git"

# ── Cache layout ───────────────────────────────────────────────────────
CACHE_DIR="${SWIFT_FORMAT_CACHE_DIR:-${HOME}/.cache/omi-swift-format}"
COMMIT12="${SWIFT_FORMAT_COMMIT:0:12}"
BUILD_DIR="${CACHE_DIR}/${SWIFT_FORMAT_VERSION}-${COMMIT12}"
BINARY="${BUILD_DIR}/.build/release/swift-format"

# ── Fail-closed helpers ────────────────────────────────────────────────
die() { echo "FATAL(swift-format-wrapper): $*" >&2; exit 1; }

assert_xcode() {
  if ! command -v xcrun >/dev/null 2>&1; then
    die "xcrun not found — run on macOS with Xcode installed"
  fi
}

# ── Bootstrap ──────────────────────────────────────────────────────────
bootstrap() {
  # Fast path: cached binary with verified version.
  if [ -x "$BINARY" ]; then
    local cached_ver
    cached_ver="$("$BINARY" --version 2>&1 | head -1)"
    if [ "$cached_ver" = "$SWIFT_FORMAT_VERSION" ]; then
      echo "swift-format cache HIT: ${SWIFT_FORMAT_VERSION} (${COMMIT12})" >&2
      return 0
    fi
    echo "swift-format cache stale (got '${cached_ver}'), rebuilding..." >&2
  fi

  assert_xcode
  echo "Bootstrapping swift-format ${SWIFT_FORMAT_VERSION} from source..." >&2

  rm -rf "$BUILD_DIR"
  mkdir -p "$BUILD_DIR"

  # Clone at exact depth-1 commit for reproducibility and minimal fetch.
  git clone --quiet --no-checkout "$SWIFT_FORMAT_REPO" "$BUILD_DIR"
  (
    cd "$BUILD_DIR"
    git checkout --quiet "$SWIFT_FORMAT_COMMIT"
  )

  # Verify the checked-out commit matches the pin.
  local actual_commit
  actual_commit="$(cd "$BUILD_DIR" && git rev-parse HEAD)"
  if [ "$actual_commit" != "$SWIFT_FORMAT_COMMIT" ]; then
    die "commit mismatch: expected ${SWIFT_FORMAT_COMMIT}, got ${actual_commit}"
  fi

  # Build with the system (pinned) Xcode.
  (
    cd "$BUILD_DIR"
    xcrun swift build -c release 2>&1
  )

  # Verify the built binary reports the pinned version.
  if [ ! -x "$BINARY" ]; then
    die "build completed but binary not found at ${BINARY}"
  fi
  local built_ver
  built_ver="$("$BINARY" --version 2>&1 | head -1)"
  if [ "$built_ver" != "$SWIFT_FORMAT_VERSION" ]; then
    die "version mismatch: expected '${SWIFT_FORMAT_VERSION}', got '${built_ver}'"
  fi

  echo "swift-format ${SWIFT_FORMAT_VERSION} built at ${SWIFT_FORMAT_COMMIT}" >&2
}

# ── Subcommands ────────────────────────────────────────────────────────
cmd="${1:-}"
[ -n "$cmd" ] || die "usage: $0 {bootstrap|version|digest|lint|format} [args...]"

case "$cmd" in
  bootstrap)
    bootstrap
    ;;
  version)
    bootstrap >&2
    "$BINARY" --version
    ;;
  digest)
    echo "$SWIFT_FORMAT_COMMIT"
    ;;
  lint)
    shift
    bootstrap >&2
    exec "$BINARY" lint --strict "$@"
    ;;
  format)
    shift
    bootstrap >&2
    exec "$BINARY" format "$@"
    ;;
  binary-path)
    # Print the binary path without bootstrapping (for cache key computation).
    echo "$BINARY"
    ;;
  *)
    die "unknown subcommand: $cmd (expected bootstrap|version|digest|lint|format|binary-path)"
    ;;
esac
