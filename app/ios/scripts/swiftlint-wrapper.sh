#!/usr/bin/env bash
# Use the repository's SHA-verified SwiftLint 0.65.0 binary and a portable baseline.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
IOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ROOT="$(cd "$IOS_DIR/../.." && pwd)"
DESKTOP_WRAPPER="$ROOT/desktop/macos/scripts/swiftlint-wrapper.sh"
"$DESKTOP_WRAPPER" bootstrap
DIGEST="$("$DESKTOP_WRAPPER" digest)"
BINARY="${SWIFTLINT_CACHE_DIR:-${HOME}/.cache/omi-swiftlint}/0.65.0-${DIGEST:0:12}/swiftlint"
[ -x "$BINARY" ] || { echo "missing verified SwiftLint binary" >&2; exit 1; }
case "${1:-}" in
  lint)
    shift
    TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/omi-ios-swiftlint.XXXXXX")"
    trap 'rm -rf "$TEMP_DIR"' EXIT
    python3 "$SCRIPT_DIR/prepare-swiftlint-baseline.py" "$IOS_DIR/.swiftlint-baseline.json" "$IOS_DIR" "$TEMP_DIR/baseline.json"
    cd "$IOS_DIR"
    "$BINARY" lint --strict --config "$IOS_DIR/.swiftlint.yml" --baseline "$TEMP_DIR/baseline.json" "$@"
    ;;
  bootstrap) ;;
  *) echo "usage: $0 {bootstrap|lint}" >&2; exit 2 ;;
esac
