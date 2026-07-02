#!/usr/bin/env bash
#
# Generate a firmware GitHub Release body, including the KEY_VALUE block that
# backend/routers/firmware.py parses to serve OTA updates.
#
# Inputs via environment:
#   TITLE                 release title heading (required)
#   VER                   release_firmware_version, e.g. 3.0.20 (required)
#   CHANGELOG             pipe-separated changelog, e.g. "Fix audio|Battery"
#   MIN_FW                minimum_firmware_required (optional; line omitted if blank)
#   MIN_APP               minimum_app_version (optional)
#   MIN_APP_CODE          minimum_app_version_code (optional)
#   OTA_STEPS             ota_update_steps, comma-separated (optional)
#   IS_LEGACY_SECURE_DFU  "True"/"False" to emit the line; blank to omit it
#   HOW_TO_FLASH          optional multiline "How to Flash" section
#   OUT                   output file path (required)
#
# Contract notes (verified against backend/routers/firmware.py):
#   - release_firmware_version is REQUIRED or the release is silently dropped.
#   - changelog is split on '|'; ota_update_steps is split on ','.
#   - is_legacy_secure_dfu must be the literal True/False (CV1=False MCUboot;
#     DK2 omits it so the backend defaults it to True = Adafruit secure DFU).
#
set -euo pipefail

: "${TITLE:?}"
: "${VER:?}"
: "${OUT:?}"

{
  echo "## $TITLE"
  echo
  echo "### What's Changed"
  changelog_emitted=0
  IFS='|' read -ra _items <<< "${CHANGELOG:-}"
  for _it in "${_items[@]}"; do
    _t="$(printf '%s' "$_it" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    if [ -n "$_t" ]; then
      echo "- $_t"
      changelog_emitted=1
    fi
  done
  if [ "$changelog_emitted" -eq 0 ]; then
    echo "- Bug fixes and improvements"
  fi
  echo

  if [ -n "${HOW_TO_FLASH:-}" ]; then
    echo "### How to Flash"
    printf '%s\n' "$HOW_TO_FLASH"
    echo
  fi

  echo "<!-- KEY_VALUE_START"
  echo "release_firmware_version:$VER"
  if [ -n "${MIN_FW:-}" ];       then echo "minimum_firmware_required:$MIN_FW"; fi
  if [ -n "${MIN_APP:-}" ];      then echo "minimum_app_version:$MIN_APP"; fi
  if [ -n "${MIN_APP_CODE:-}" ]; then echo "minimum_app_version_code:$MIN_APP_CODE"; fi
  if [ -n "${OTA_STEPS:-}" ];    then echo "ota_update_steps:$OTA_STEPS"; fi
  if [ -n "${IS_LEGACY_SECURE_DFU:-}" ]; then echo "is_legacy_secure_dfu:$IS_LEGACY_SECURE_DFU"; fi
  echo "changelog:${CHANGELOG:-Bug fixes and improvements}"
  echo "KEY_VALUE_END -->"
} > "$OUT"

echo "Wrote release body to $OUT:"
echo "----------------------------------------"
cat "$OUT"
echo "----------------------------------------"
