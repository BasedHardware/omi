#!/usr/bin/env bash
# Pinned SwiftLint bootstrap and lint runner (#9843 Ticket 06).
#
# The SwiftPM build-tool plugin cannot run in release builds because SwiftPM
# rejects prebuild commands whose executable is itself source-built. This
# wrapper instead fetches the upstream universal macOS release binary and
# verifies its exact SHA-256 before it can run. That preserves a pinned,
# reproducible lint input without compiling SwiftLint's dependency graph on
# every cache miss.
set -euo pipefail

SWIFTLINT_VERSION="0.65.0"
SWIFTLINT_RELEASE_URL="https://github.com/realm/SwiftLint/releases/download/${SWIFTLINT_VERSION}/portable_swiftlint.zip"
SWIFTLINT_RELEASE_SHA256="d6cb0aa7a2f5f1ef306fc9e37bcb54dc9a26facc8f7784ac0c3dd3eccf5c6ba6"
SWIFTLINT_BINARY_SHA256="06bdd57b59087dde8680ba6a62452defd71babd0513023f19ddfc6773708ba34"

CACHE_DIR="${SWIFTLINT_CACHE_DIR:-${HOME}/.cache/omi-swiftlint}"
SHA12="${SWIFTLINT_RELEASE_SHA256:0:12}"
INSTALL_DIR="${CACHE_DIR}/${SWIFTLINT_VERSION}-${SHA12}"
BINARY="${INSTALL_DIR}/swiftlint"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DESKTOP_DIR="$MACOS_DIR/Desktop"
CONFIG_FILE="$DESKTOP_DIR/.swiftlint.yml"
BASELINE_FILE="$DESKTOP_DIR/.swiftlint-baseline.json"
BASELINE_PREPARER="$SCRIPT_DIR/prepare-swiftlint-baseline.py"

die() { echo "FATAL(swiftlint-wrapper): $*" >&2; exit 1; }

verified_cached_binary() {
  [ -f "$BINARY" ] && [ ! -L "$BINARY" ] || return 1

  local binary_sha cached_version
  binary_sha="$(shasum -a 256 "$BINARY" | awk '{print $1}')"
  [ "$binary_sha" = "$SWIFTLINT_BINARY_SHA256" ] || return 1

  cached_version="$("$BINARY" version 2>&1 | sed -n '1p')"
  [ "$cached_version" = "$SWIFTLINT_VERSION" ]
}

bootstrap() {
  command -v shasum >/dev/null 2>&1 || die "shasum not found"

  if [ -e "$BINARY" ] || [ -L "$BINARY" ]; then
    if verified_cached_binary; then
      echo "swiftlint cache HIT: ${SWIFTLINT_VERSION} (${SHA12})" >&2
      return 0
    fi
    echo "swiftlint cache integrity check failed; rebuilding..." >&2
  fi

  command -v curl >/dev/null 2>&1 || die "curl not found"
  command -v unzip >/dev/null 2>&1 || die "unzip not found"

  mkdir -p "$CACHE_DIR"
  local temp_dir archive actual_sha archive_entries
  temp_dir="$(mktemp -d "${CACHE_DIR}/.swiftlint-download.XXXXXX")"
  archive="${temp_dir}/portable_swiftlint.zip"

  echo "Fetching verified SwiftLint ${SWIFTLINT_VERSION} release binary..." >&2
  if ! curl --fail --location --proto '=https' --tlsv1.2 --retry 3 --silent --show-error \
    --output "$archive" "$SWIFTLINT_RELEASE_URL"; then
    rm -rf "$temp_dir"
    die "failed to download ${SWIFTLINT_RELEASE_URL}"
  fi

  actual_sha="$(shasum -a 256 "$archive" | awk '{print $1}')"
  if [ "$actual_sha" != "$SWIFTLINT_RELEASE_SHA256" ]; then
    rm -rf "$temp_dir"
    die "SHA-256 mismatch: expected ${SWIFTLINT_RELEASE_SHA256}, got ${actual_sha}"
  fi

  archive_entries="$(unzip -Z -1 "$archive" | sort)"
  if [ "$archive_entries" != $'LICENSE\nswiftlint' ]; then
    rm -rf "$temp_dir"
    die "unexpected release archive layout"
  fi

  unzip -q "$archive" -d "$temp_dir/extract"
  [ -f "$temp_dir/extract/swiftlint" ] && [ ! -L "$temp_dir/extract/swiftlint" ] || {
    rm -rf "$temp_dir"
    die "release archive does not contain a regular swiftlint binary"
  }
  chmod 755 "$temp_dir/extract/swiftlint"

  local binary_sha built_version
  binary_sha="$(shasum -a 256 "$temp_dir/extract/swiftlint" | awk '{print $1}')"
  if [ "$binary_sha" != "$SWIFTLINT_BINARY_SHA256" ]; then
    rm -rf "$temp_dir"
    die "binary SHA-256 mismatch: expected ${SWIFTLINT_BINARY_SHA256}, got ${binary_sha}"
  fi

  built_version="$("$temp_dir/extract/swiftlint" version 2>&1 | sed -n '1p')"
  if [ "$built_version" != "$SWIFTLINT_VERSION" ]; then
    rm -rf "$temp_dir"
    die "version mismatch: expected '${SWIFTLINT_VERSION}', got '${built_version}'"
  fi

  rm -rf "$INSTALL_DIR"
  mv "$temp_dir/extract" "$INSTALL_DIR"
  rm -rf "$temp_dir"
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
    echo "$SWIFTLINT_RELEASE_SHA256"
    ;;
  lint)
    shift
    bootstrap >&2
    command -v python3 >/dev/null 2>&1 || die "python3 not found"
    [ -f "$BASELINE_PREPARER" ] || die "baseline preparer not found: $BASELINE_PREPARER"
    local_baseline_dir="$(mktemp -d "${TMPDIR:-/tmp}/omi-swiftlint-baseline.XXXXXX")"
    trap 'rm -rf "$local_baseline_dir"' EXIT
    if ! python3 "$BASELINE_PREPARER" \
      --input "$BASELINE_FILE" \
      --desktop-dir "$DESKTOP_DIR" \
      --output "$local_baseline_dir/baseline.json"; then
      die "failed to prepare a portable SwiftLint baseline"
    fi
    cd "$DESKTOP_DIR"
    "$BINARY" lint --strict --config "$CONFIG_FILE" --baseline "$local_baseline_dir/baseline.json" "$@"
    ;;
  *)
    die "usage: $0 {bootstrap|version|digest|lint}"
    ;;
esac
