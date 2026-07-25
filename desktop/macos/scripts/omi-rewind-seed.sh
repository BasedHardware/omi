#!/usr/bin/env bash
# omi-rewind-seed.sh — take a one-time, consistent Rewind snapshot for a named bundle.
#
# Auth and settings make a named bundle feel like Omi Dev, but Rewind history is
# local. Copy a safe SQLite snapshot plus the frame assets on first launch so a
# QA bundle starts with the same user history while keeping a separate writable
# profile. Existing named profiles are left alone unless OMI_FORCE_REWIND_SEED=1.
#
# Usage: omi-rewind-seed.sh <target-bundle-id>
set -euo pipefail

TARGET_BUNDLE_ID="${1:?usage: omi-rewind-seed.sh <target-bundle-id>}"
SOURCE_ROOT="${OMI_REWIND_SEED_SOURCE_ROOT:-$HOME/Library/Application Support/Omi}"
TARGET_ROOT="${OMI_REWIND_SEED_TARGET_ROOT:-$HOME/Library/Application Support/Omi Dev Bundles/$TARGET_BUNDLE_ID}"
FORCE_SEED="${OMI_FORCE_REWIND_SEED:-0}"

if [ -n "${OMI_REWIND_SEED_USER_ID:-}" ]; then
  USER_ID="$OMI_REWIND_SEED_USER_ID"
else
  USER_ID="$(defaults read "$TARGET_BUNDLE_ID" auth_userId 2>/dev/null || true)"
fi

if [ -z "$USER_ID" ]; then
  echo "Rewind seed skipped: named bundle has no signed-in user"
  exit 0
fi

case "$USER_ID" in
  *[!A-Za-z0-9_-]* )
    echo "Rewind seed skipped: unsupported local profile identifier" >&2
    exit 0
    ;;
esac

SOURCE_USER_DIR="$SOURCE_ROOT/users/$USER_ID"
TARGET_USERS_DIR="$TARGET_ROOT/users"
TARGET_USER_DIR="$TARGET_USERS_DIR/$USER_ID"
SOURCE_DB="$SOURCE_USER_DIR/omi.db"

if [ ! -f "$SOURCE_DB" ]; then
  echo "Rewind seed skipped: no Omi Dev Rewind profile for this user"
  exit 0
fi

if [ "$SOURCE_USER_DIR" = "$TARGET_USER_DIR" ]; then
  echo "Rewind seed skipped: source and target profiles are identical" >&2
  exit 0
fi

if [ -f "$TARGET_USER_DIR/omi.db" ] && [ "$FORCE_SEED" != "1" ]; then
  echo "Rewind seed skipped: named bundle already has a Rewind profile"
  exit 0
fi

mkdir -p "$TARGET_USERS_DIR"
STAGING_DIR="$(mktemp -d "$TARGET_USERS_DIR/.rewind-seed.XXXXXX")"
cleanup() {
  [ -z "${STAGING_DIR:-}" ] || rm -rf "$STAGING_DIR"
}
trap cleanup EXIT

python3 - "$SOURCE_USER_DIR" "$STAGING_DIR" <<'PY'
from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])
source_db = source / "omi.db"
target_db = target / "omi.db"

# SQLite's backup API reads a coherent snapshot even while Omi Dev is writing
# through WAL. Copying omi.db plus its WAL/SHM files would not have that safety.
source_connection = sqlite3.connect(f"{source_db.as_uri()}?mode=ro", uri=True)
target_connection = sqlite3.connect(target_db)
try:
    source_connection.backup(target_connection)
    frame_count = target_connection.execute("SELECT COUNT(*) FROM screenshots").fetchone()[0]
finally:
    target_connection.close()
    source_connection.close()

# These are the Rewind assets referenced by relative database paths. Backups are
# useful for parity with Omi Dev and remain independent after the import.
for name in ("Screenshots", "Videos", "backups"):
    source_item = source / name
    if source_item.is_dir():
        shutil.copytree(source_item, target / name, copy_function=shutil.copy2)

for name in ("memory-graph-layout.json",):
    source_item = source / name
    if source_item.is_file():
        shutil.copy2(source_item, target / name)

bytes_copied = sum(path.stat().st_size for path in target.rglob("*") if path.is_file())
print(f"Rewind seed complete: frames={frame_count} bytes={bytes_copied}")
PY

if [ -e "$TARGET_USER_DIR" ]; then
  if [ "$FORCE_SEED" != "1" ]; then
    echo "Rewind seed skipped: named bundle profile exists without a database" >&2
    exit 0
  fi
  PRESERVED_DIR="$TARGET_USERS_DIR/.rewind-before-seed-$(date +%Y%m%d%H%M%S)-$$"
  mv "$TARGET_USER_DIR" "$PRESERVED_DIR"
  echo "Preserved existing named-bundle Rewind profile before reseeding"
fi

mv "$STAGING_DIR" "$TARGET_USER_DIR"
STAGING_DIR=""
