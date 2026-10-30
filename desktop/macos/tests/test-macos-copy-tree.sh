#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=../scripts/macos-copy-tree.sh
source "$SCRIPT_DIR/../scripts/macos-copy-tree.sh"
# shellcheck source=../scripts/agent-runtime-cache.sh
source "$SCRIPT_DIR/../scripts/agent-runtime-cache.sh"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/omi-macos-copy-tree.XXXXXX")"
trap 'rm -rf "$TMP_ROOT"' EXIT

mkdir -p "$TMP_ROOT/src/nested"
python3 - "$TMP_ROOT/src/nested/payload.bin" <<'PY'
import sys
with open(sys.argv[1], "wb") as handle:
    handle.write(b"payload-v1\n" * 1024)
PY
printf 'sidecar\n' >"$TMP_ROOT/src/readme.txt"

macos_copy_tree "$TMP_ROOT/src" "$TMP_ROOT/dest"
cmp -s "$TMP_ROOT/src/nested/payload.bin" "$TMP_ROOT/dest/nested/payload.bin" || fail "copied payload bytes differ"
cmp -s "$TMP_ROOT/src/readme.txt" "$TMP_ROOT/dest/readme.txt" || fail "copied sidecar bytes differ"

if [ "$(uname -s)" = "Darwin" ]; then
  macos_ditto_supports_clone || fail "this macOS ditto does not advertise --clone"
  arc_same_clone "$TMP_ROOT/src/nested/payload.bin" "$TMP_ROOT/dest/nested/payload.bin" || fail "ditto --clone did not share an APFS clone"
  # Resource-fork suppression stays on the clone path. A Finder resource fork
  # written beside the payload must not be recreated by the bundle copy.
  xattr -w com.apple.ResourceFork "$(printf 'resource-fork')" "$TMP_ROOT/src/readme.txt"
  xattr -p com.apple.ResourceFork "$TMP_ROOT/src/readme.txt" >/dev/null || fail "could not attach a resource fork for the --norsrc check"
  rm -rf "$TMP_ROOT/dest"
  macos_copy_tree "$TMP_ROOT/src" "$TMP_ROOT/dest"
  if xattr -p com.apple.ResourceFork "$TMP_ROOT/dest/readme.txt" >/dev/null 2>&1; then
    fail "macos_copy_tree preserved a resource fork"
  fi
  arc_same_clone "$TMP_ROOT/src/nested/payload.bin" "$TMP_ROOT/dest/nested/payload.bin" || fail "resource-fork cleanup broke the APFS clone"
fi

echo "macos copy tree tests passed"
