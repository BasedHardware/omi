#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
SCRIPT="$MACOS_DIR/scripts/publish-desktop-debug-symbols.sh"
TEST_ROOT="$(mktemp -d /tmp/omi-dsym-test.XXXXXX)"
trap 'rm -rf "$TEST_ROOT"' EXIT

BIN_DIR="$TEST_ROOT/bin"
mkdir -p "$BIN_DIR"
touch "$TEST_ROOT/Omi"

cat > "$BIN_DIR/xcrun" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == "dsymutil" ]]; then
  mkdir -p "$4/Contents/Resources/DWARF"
  touch "$4/Contents/Resources/DWARF/Omi"
  exit 0
fi
if [[ "$1" == "dwarfdump" && "$2" == "--uuid" ]]; then
  if [[ "${OMI_TEST_MISMATCH:-0}" == "1" && "$3" == *.dSYM ]]; then
    echo "UUID: BBBBBBBB-BBBB-BBBB-BBBB-BBBBBBBBBBBB (arm64) $3"
  else
    echo "UUID: AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA (arm64) $3"
  fi
  echo "UUID: CCCCCCCC-CCCC-CCCC-CCCC-CCCCCCCCCCCC (x86_64) $3"
  exit 0
fi
exit 64
EOF

cat > "$BIN_DIR/ditto" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf 'zip' > "${@: -1}"
EOF

chmod +x "$BIN_DIR/xcrun" "$BIN_DIR/ditto"

export PATH="$BIN_DIR:/usr/bin:/bin"
DSYM="$TEST_ROOT/Omi.app.dSYM"
ARCHIVE="$TEST_ROOT/Omi.dSYM.zip"

"$SCRIPT" generate --binary "$TEST_ROOT/Omi" --dsym "$DSYM" --archive "$ARCHIVE"
[[ -s "$ARCHIVE" ]]

# The upload modes were removed with Sentry; they must now be rejected by usage.
if "$SCRIPT" upload --binary "$TEST_ROOT/Omi" --dsym "$DSYM" \
  >"$TEST_ROOT/upload-removed.out" 2>&1
then
  echo "ERROR: upload mode still accepted after Sentry removal" >&2
  exit 1
fi
grep -Fq 'Usage:' "$TEST_ROOT/upload-removed.out"

if "$SCRIPT" upload-best-effort --binary "$TEST_ROOT/Omi" --dsym "$DSYM" \
  >"$TEST_ROOT/best-effort-removed.out" 2>&1
then
  echo "ERROR: upload-best-effort mode still accepted after Sentry removal" >&2
  exit 1
fi
grep -Fq 'Usage:' "$TEST_ROOT/best-effort-removed.out"

if OMI_TEST_MISMATCH=1 "$SCRIPT" generate --binary "$TEST_ROOT/Omi" \
  --dsym "$TEST_ROOT/mismatch.dSYM" --archive "$TEST_ROOT/mismatch.zip" \
  >"$TEST_ROOT/mismatch.out" 2>&1
then
  echo "ERROR: mismatched UUIDs were accepted" >&2
  exit 1
fi
grep -Fq 'dSYM UUIDs do not exactly match' "$TEST_ROOT/mismatch.out"

echo "desktop debug-symbol publication tests passed"
