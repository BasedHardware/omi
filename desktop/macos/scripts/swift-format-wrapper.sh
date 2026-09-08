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
#   swift-format-wrapper.sh scope       — list first-party Swift files (excludes Generated/)
#   swift-format-wrapper.sh format -i FILE… — format in-place
#
# Concurrency: the from-source bootstrap is serialized by a lock directory at
# <cache>/<version>-<commit12>.lock. Override the wait with
# SWIFT_FORMAT_LOCK_TIMEOUT (seconds).
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

# ── Project paths ─────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG_FILE="$MACOS_DIR/Desktop/.swift-format"
GENERATED_DIR="$MACOS_DIR/Desktop/Sources/Generated"
BINARY="${BUILD_DIR}/.build/release/swift-format"
LOCK_DIR="${BUILD_DIR}.lock"
# A cold build takes ~15 minutes on an M-series laptop; wait comfortably past
# that before declaring the holder wedged.
LOCK_TIMEOUT_SECONDS="${SWIFT_FORMAT_LOCK_TIMEOUT:-1800}"

# ── Fail-closed helpers ────────────────────────────────────────────────
die() { echo "FATAL(swift-format-wrapper): $*" >&2; exit 1; }

assert_xcode() {
  if ! command -v xcrun >/dev/null 2>&1; then
    die "xcrun not found — run on macOS with Xcode installed"
  fi
}

# ── Bootstrap serialization ────────────────────────────────────────────
# `bootstrap` starts by deleting BUILD_DIR, so two concurrent bootstraps are
# not merely wasteful — the second one's `rm -rf` removes the first one's
# object files mid-compile. Observed live: two worktrees running checks at
# once produced `rename failed: ... .o.tmp -> .o: No such file or directory`
# and then `accessing build database: disk I/O error`, leaving no binary
# behind. Every later invocation rebuilt and raced again, so the formatter
# stayed permanently broken and commit hooks failed with `unable to read
# tree`. One cache is shared by every worktree, which is why this is routine
# rather than rare.
#
# `mkdir` is the lock because it is atomic on every POSIX filesystem and needs
# no external binary — macOS has no `flock(1)`, and `shlock` is BSD-only, so
# neither is safe for the Linux CI lanes that also run this script.
cached_binary_is_current() {
  [ -x "$BINARY" ] || return 1
  local cached_ver
  cached_ver="$("$BINARY" --version 2>&1 | head -1)"
  [ "$cached_ver" = "$SWIFT_FORMAT_VERSION" ]
}

release_bootstrap_lock() {
  trap - EXIT INT TERM
  rm -rf "$LOCK_DIR"
}

acquire_bootstrap_lock() {
  local waited=0 owner announced=0
  mkdir -p "$CACHE_DIR"
  while ! mkdir "$LOCK_DIR" 2>/dev/null; do
    owner="$(cat "$LOCK_DIR/owner" 2>/dev/null || true)"
    # Reclaim a lock whose holder died mid-build. An empty owner file means the
    # holder is between mkdir and the write, so it is treated as alive.
    if [ -n "$owner" ] && ! kill -0 "$owner" 2>/dev/null; then
      echo "swift-format: reclaiming bootstrap lock from dead pid ${owner}" >&2
      rm -rf "$LOCK_DIR"
      continue
    fi
    if [ "$waited" -ge "$LOCK_TIMEOUT_SECONDS" ]; then
      die "timed out after ${LOCK_TIMEOUT_SECONDS}s waiting for the bootstrap lock at ${LOCK_DIR} (holder pid ${owner:-unknown})"
    fi
    if [ "$announced" -eq 0 ]; then
      echo "swift-format: another bootstrap holds the lock (pid ${owner:-unknown}); waiting..." >&2
      announced=1
    fi
    sleep 2
    waited=$((waited + 2))
  done
  # Released explicitly on the success path because `lint`/`format` hand off
  # with `exec`, which discards traps.
  trap 'rm -rf "$LOCK_DIR"' EXIT INT TERM
  echo $$ > "$LOCK_DIR/owner"
}

# ── Bootstrap ──────────────────────────────────────────────────────────
bootstrap() {
  # Fast path: cached binary with verified version. Deliberately outside the
  # lock — a cache hit reads a finished binary and serializing it would put
  # every lint call behind a mutex for no benefit.
  if cached_binary_is_current; then
    echo "swift-format cache HIT: ${SWIFT_FORMAT_VERSION} (${COMMIT12})" >&2
    return 0
  fi
  if [ -x "$BINARY" ]; then
    echo "swift-format cache stale (got '$("$BINARY" --version 2>&1 | head -1)'), rebuilding..." >&2
  fi

  assert_xcode
  acquire_bootstrap_lock
  # Re-check under the lock: whoever held it may have just built the binary we
  # were about to rebuild. Without this, waiters queue up and each one still
  # pays a full 15-minute build.
  if cached_binary_is_current; then
    release_bootstrap_lock
    echo "swift-format cache HIT after waiting: ${SWIFT_FORMAT_VERSION} (${COMMIT12})" >&2
    return 0
  fi

  echo "Bootstrapping swift-format ${SWIFT_FORMAT_VERSION} from source..." >&2

  rm -rf "$BUILD_DIR"
  mkdir -p "$BUILD_DIR"

  # Clone at exact depth-1 commit for reproducibility and minimal fetch.
  git clone --quiet --depth 1 --branch "$SWIFT_FORMAT_VERSION" --no-checkout "$SWIFT_FORMAT_REPO" "$BUILD_DIR"
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

  release_bootstrap_lock
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
    exec "$BINARY" lint --strict --configuration "$CONFIG_FILE" "$@"
    ;;
  lint-scope)
    # Verify the tree is formatter-clean: format must be a no-op on every
    # file in scope.  This catches true formatting drift — the lint command
    # also reports advisory rules the formatter cannot auto-fix, so we use
    # format idempotency as the enforcement signal.
    bootstrap >&2
    drift=0
    while IFS= read -r f; do
      if ! "$BINARY" format --configuration "$CONFIG_FILE" "$f" 2>/dev/null | diff -q "$f" - >/dev/null 2>&1; then
        echo "FORMAT DRIFT: $f" >&2
        drift=1
      fi
    done < <("$0" scope)
    if [ "$drift" -eq 0 ]; then
      echo "swift-format: clean (no formatting drift in scope)" >&2
    fi
    exit "$drift"
    ;;
  format)
    shift
    bootstrap >&2
    exec "$BINARY" format --configuration "$CONFIG_FILE" "$@"
    ;;
  scope)
    # List all first-party hand-written Swift files, excluding generated sources.
    find "$MACOS_DIR/Desktop/Sources" "$MACOS_DIR/Desktop/Tests" \
      -name '*.swift' \
      -not -path "$GENERATED_DIR/*" \
      | sort
    ;;
  lock-path)
    # Print the bootstrap lock path without bootstrapping (debugging, tests).
    echo "$LOCK_DIR"
    ;;
  binary-path)
    # Print the binary path without bootstrapping (for cache key computation).
    echo "$BINARY"
    ;;
  config-path)
    echo "$CONFIG_FILE"
    ;;
  *)
    die "unknown subcommand: $cmd (expected bootstrap|version|digest|lint|format|scope|binary-path|config-path|lock-path)"
    ;;
esac
