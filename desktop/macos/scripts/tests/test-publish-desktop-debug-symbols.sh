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

cat > "$BIN_DIR/npx" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" > "$OMI_TEST_NPX_ARGS"
EOF
chmod +x "$BIN_DIR/xcrun" "$BIN_DIR/ditto" "$BIN_DIR/npx"

export PATH="$BIN_DIR:/usr/bin:/bin"
DSYM="$TEST_ROOT/Omi.app.dSYM"
ARCHIVE="$TEST_ROOT/Omi.dSYM.zip"

"$SCRIPT" generate --binary "$TEST_ROOT/Omi" --dsym "$DSYM" --archive "$ARCHIVE"
[[ -s "$ARCHIVE" ]]

export SENTRY_AUTH_TOKEN="test-token"
export OMI_TEST_NPX_ARGS="$TEST_ROOT/npx-args"
"$SCRIPT" upload --binary "$TEST_ROOT/Omi" --dsym "$DSYM"
grep -Fq '@sentry/cli@2.52.0 debug-files upload --org omi-nk3 --project omi-desktop --wait' \
  "$OMI_TEST_NPX_ARGS"

if OMI_TEST_MISMATCH=1 "$SCRIPT" upload --binary "$TEST_ROOT/Omi" --dsym "$DSYM" \
  >"$TEST_ROOT/mismatch.out" 2>&1
then
  echo "ERROR: mismatched UUIDs were accepted" >&2
  exit 1
fi
grep -Fq 'dSYM UUIDs do not exactly match' "$TEST_ROOT/mismatch.out"

echo "desktop debug-symbol publication tests passed"
