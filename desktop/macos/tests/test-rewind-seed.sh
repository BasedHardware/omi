#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SEED_SCRIPT="$MACOS_DIR/scripts/omi-rewind-seed.sh"

TMPDIR="$(mktemp -d)"
cleanup() { rm -rf "$TMPDIR"; }
trap cleanup EXIT

source_root="$TMPDIR/source"
target_root="$TMPDIR/target"
user_id="rewind-test-user"
source_user="$source_root/users/$user_id"
target_user="$target_root/users/$user_id"
mkdir -p "$source_user/Videos" "$source_user/Screenshots" "$source_user/backups"

python3 - "$source_user/omi.db" <<'PY'
import sqlite3
import sys

connection = sqlite3.connect(sys.argv[1])
connection.execute("CREATE TABLE screenshots (id INTEGER PRIMARY KEY, timestamp TEXT)")
connection.execute("INSERT INTO screenshots (timestamp) VALUES ('2026-07-16T00:00:00Z')")
connection.commit()
connection.close()
PY
printf 'video fixture' >"$source_user/Videos/chunk.mp4"
printf 'screenshot fixture' >"$source_user/Screenshots/legacy.jpg"
printf 'backup fixture' >"$source_user/backups/omi.db"
printf '{"positions":[]}' >"$source_user/memory-graph-layout.json"

env \
  OMI_REWIND_SEED_USER_ID="$user_id" \
  OMI_REWIND_SEED_SOURCE_ROOT="$source_root" \
  OMI_REWIND_SEED_TARGET_ROOT="$target_root" \
  "$SEED_SCRIPT" com.omi.omi-rewind-seed >"$TMPDIR/first.out"

grep -q 'Rewind seed complete: frames=1' "$TMPDIR/first.out"
test -f "$target_user/omi.db"
test -f "$target_user/Videos/chunk.mp4"
test -f "$target_user/Screenshots/legacy.jpg"
test -f "$target_user/backups/omi.db"
test -f "$target_user/memory-graph-layout.json"

python3 - "$target_user/omi.db" <<'PY'
import sqlite3
import sys

connection = sqlite3.connect(sys.argv[1])
assert connection.execute("SELECT COUNT(*) FROM screenshots").fetchone()[0] == 1
connection.close()
PY

printf 'named-only frame' >"$target_user/Videos/named-only.mp4"
env \
  OMI_REWIND_SEED_USER_ID="$user_id" \
  OMI_REWIND_SEED_SOURCE_ROOT="$source_root" \
  OMI_REWIND_SEED_TARGET_ROOT="$target_root" \
  "$SEED_SCRIPT" com.omi.omi-rewind-seed >"$TMPDIR/second.out"
grep -q 'already has a Rewind profile' "$TMPDIR/second.out"
test -f "$target_user/Videos/named-only.mp4"

env \
  OMI_FORCE_REWIND_SEED=1 \
  OMI_REWIND_SEED_USER_ID="$user_id" \
  OMI_REWIND_SEED_SOURCE_ROOT="$source_root" \
  OMI_REWIND_SEED_TARGET_ROOT="$target_root" \
  "$SEED_SCRIPT" com.omi.omi-rewind-seed >"$TMPDIR/force.out"
grep -q 'Preserved existing named-bundle Rewind profile' "$TMPDIR/force.out"
grep -q 'Rewind seed complete: frames=1' "$TMPDIR/force.out"

shopt -s nullglob
preserved=("$target_root/users"/.rewind-before-seed-*)
test "${#preserved[@]}" -eq 1
test -f "${preserved[0]}/Videos/named-only.mp4"
test ! -f "$target_user/Videos/named-only.mp4"

echo "rewind-seed tests passed"
