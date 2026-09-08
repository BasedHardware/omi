#!/usr/bin/env bash
# Reusable test-build index-store contract (#9843 Ticket 09).
#
# Builds tests once with an explicit index-store path, emits a marker keyed by
# target/toolchain/lockfile, and asserts the path exists. Periphery (Ticket 19)
# consumes this path with --skip-build.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PACKAGE_PATH="${1:-$MACOS_DIR/Desktop}"
INDEX_DIR="$PACKAGE_PATH/.build/index-store"

if ! command -v xcrun >/dev/null 2>&1; then
  echo "FATAL: requires macOS with Xcode" >&2
  exit 1
fi

echo "Building tests with index store..." >&2
xcrun swift build --package-path "$PACKAGE_PATH" --build-tests 2>&1 | tail -3

# Find the actual index store path (SwiftPM puts it under .build/<config>/index/db)
INDEX_STORE=""
for candidate in \
  "$PACKAGE_PATH/.build/debug/index/db" \
  "$PACKAGE_PATH/.build/debug/index/store"; do
  if [ -d "$candidate" ]; then
    INDEX_STORE="$candidate"
    break
  fi
done

if [ -z "$INDEX_STORE" ]; then
  echo "FAIL: index store not found under $PACKAGE_PATH/.build/" >&2
  exit 1
fi

echo "Index store: $INDEX_STORE" >&2

# Emit marker keyed by toolchain + lockfile
TOOLCHAIN=$(xcrun swift --version 2>&1 | head -1)
LOCKFILE_HASH=$(shasum -a 256 "$PACKAGE_PATH/Package.resolved" 2>/dev/null | cut -c1-16 || echo "unknown")
MARKER="$INDEX_DIR/marker.json"

mkdir -p "$INDEX_DIR"
cat > "$MARKER" << EOF
{
  "toolchain": "$TOOLCHAIN",
  "lockfile_hash": "$LOCKFILE_HASH",
  "index_store": "$INDEX_STORE",
  "created_by": "swift-diagnostic-ledger index-store contract"
}
EOF

echo "Marker: $MARKER" >&2
echo "$INDEX_STORE"
