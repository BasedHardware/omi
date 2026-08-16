#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN="$ROOT/run.sh"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/omi-bundled-dylib.XXXXXX")"
FAKE_BIN="$TMP_ROOT/bin"
STATE="$TMP_ROOT/state"
CALLS="$TMP_ROOT/install-name-tool-calls"

cleanup() {
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

mkdir -p "$FAKE_BIN"
printf 'external\n' > "$STATE"

cat > "$FAKE_BIN/otool" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

if [ "$(cat "$TEST_STATE")" = "rewritten" ]; then
  load_path='@rpath/libwebp.7.dylib'
else
  load_path='/opt/homebrew/opt/webp/lib/libwebp.7.dylib'
fi

printf '%s:\n\t%s (compatibility version 10.0.0, current version 10.0.0)\n' "$1" "$load_path"
EOF

cat > "$FAKE_BIN/install_name_tool" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

printf '%s\n' "$@" > "$TEST_CALLS"
printf 'rewritten\n' > "$TEST_STATE"
EOF

chmod +x "$FAKE_BIN/otool" "$FAKE_BIN/install_name_tool"

REWRITE_FUNCTION="$(sed -n '/^rewrite_bundled_dylib_load_path()/,/^}/p' "$RUN")"
if [ -z "$REWRITE_FUNCTION" ]; then
  echo "FAIL: rewrite_bundled_dylib_load_path is missing from $RUN" >&2
  exit 1
fi

PATH="$FAKE_BIN:$PATH"
export PATH TEST_STATE="$STATE" TEST_CALLS="$CALLS"
eval "$REWRITE_FUNCTION"

rewrite_bundled_dylib_load_path "$TMP_ROOT/Omi Computer" "libwebp.7.dylib"

expected_calls=$'-change\n/opt/homebrew/opt/webp/lib/libwebp.7.dylib\n@rpath/libwebp.7.dylib\n'
expected_calls+="$TMP_ROOT/Omi Computer"
test "$(cat "$CALLS")" = "${expected_calls%$'\n'}"
test "$(cat "$STATE")" = "rewritten"

rewrite_bundled_dylib_load_path "$TMP_ROOT/Omi Computer" "libwebp.7.dylib"
test "$(cat "$CALLS")" = "${expected_calls%$'\n'}"

echo "PASS: bundled dylib load paths are rewritten and verified"
