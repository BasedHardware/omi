#!/bin/bash

set -e

# Resolve full path to the script's directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Relative path to the UF2 file
FILE="$SCRIPT_DIR/build/build_xiao_ble_sense_devkitv2-adafruit/zephyr/zephyr.uf2"
DEST="/Volumes/XIAO-SENSE"

if [ ! -f "$FILE" ]; then
  echo "❌ Firmware file not found: $FILE"
  exit 1
fi

echo "📄 Firmware file path: $FILE"

MOD_TIME=$(stat -f "%m" "$FILE")
NOW=$(date +%s)
DELTA=$((NOW - MOD_TIME))

echo "✅ Firmware modified: $(date -r $MOD_TIME) | $DELTA seconds ago"

if [ ! -d "$DEST" ]; then
  echo "❌ Target device not mounted at $DEST"
  exit 1
fi

cp "$FILE" "$DEST"
echo "🚀 Copied to $DEST"
