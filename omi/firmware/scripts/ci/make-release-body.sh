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
#   ROLLOUT_PERCENT       optional 0-100 cohort (CV1 workflow supplies 1)
#   BLOCKED               optional true/false kill switch
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

# Match line stripping and first-colon splitting in
# backend/utils/github_releases.py:extract_key_value_pairs. Validate every
# interpolated input, including prose outside the block, before writing a file.
python3 - <<'PY'
import os

keys = {
    'release_firmware_version', 'minimum_firmware_required', 'minimum_app_version',
    'minimum_app_version_code', 'ota_update_steps', 'is_legacy_secure_dfu',
    'rollout_percent', 'blocked', 'changelog',
}
for name in (
    'TITLE', 'VER', 'CHANGELOG', 'MIN_FW', 'MIN_APP', 'MIN_APP_CODE',
    'OTA_STEPS', 'IS_LEGACY_SECURE_DFU', 'ROLLOUT_PERCENT', 'BLOCKED', 'HOW_TO_FLASH',
):
    value = os.environ.get(name, '')
    if 'KEY_VALUE_START' in value or 'KEY_VALUE_END' in value:
        raise SystemExit(f'{name} contains a release metadata delimiter')
    for line in value.split('\n'):
        parts = line.strip().split(':', 1)
        if len(parts) == 2 and parts[0].strip() in keys:
            raise SystemExit(f'{name} contains reserved release metadata key: {parts[0].strip()}')
PY

{
  echo "## $TITLE"
  echo
  echo "### What's Changed"
  changelog_emitted=0
  IFS='|' read -ra _items <<< "${CHANGELOG:-}"
  # Bash 3.2 treats an empty read array as unbound under set -u.
  for _it in "${_items[@]:-}"; do
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
  echo "changelog:${CHANGELOG:-Bug fixes and improvements}"
  # Authoritative policy/version keys are last as defense in depth.
  echo "release_firmware_version:$VER"
  if [ -n "${MIN_FW:-}" ];       then echo "minimum_firmware_required:$MIN_FW"; fi
  if [ -n "${MIN_APP:-}" ];      then echo "minimum_app_version:$MIN_APP"; fi
  if [ -n "${MIN_APP_CODE:-}" ]; then echo "minimum_app_version_code:$MIN_APP_CODE"; fi
  if [ -n "${OTA_STEPS:-}" ];    then echo "ota_update_steps:$OTA_STEPS"; fi
  if [ -n "${IS_LEGACY_SECURE_DFU:-}" ]; then echo "is_legacy_secure_dfu:$IS_LEGACY_SECURE_DFU"; fi
  if [ -n "${ROLLOUT_PERCENT:-}" ]; then echo "rollout_percent:$ROLLOUT_PERCENT"; fi
  if [ -n "${BLOCKED:-}" ]; then echo "blocked:$BLOCKED"; fi
  echo "KEY_VALUE_END -->"
} > "$OUT"

echo "Wrote release body to $OUT:"
echo "----------------------------------------"
cat "$OUT"
echo "----------------------------------------"
