#!/usr/bin/env bash
# Shared admission boundary for Android full releases and production OTA patches.
set -euo pipefail

if [[ $# != 1 ]]; then
  echo 'Usage: admit_android_source.sh <exact-source-sha>' >&2
  exit 2
fi
ANDROID_ADMISSION_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ANDROID_ADMISSION_SOURCE="$1"
if [[ "$(git -C "$ANDROID_ADMISSION_ROOT" rev-parse HEAD)" != "$ANDROID_ADMISSION_SOURCE" ]]; then
  echo 'Android admission source must equal the checked-out commit.' >&2
  exit 1
fi
ANDROID_ADMISSION_PROOF="$(mktemp)"
trap 'rm -f "$ANDROID_ADMISSION_PROOF"' EXIT
python3 "$ANDROID_ADMISSION_ROOT/.github/scripts/collect_mobile_release_admission.py" \
  --platform android --sha "$ANDROID_ADMISSION_SOURCE" \
  --repository "${GITHUB_REPOSITORY:-BasedHardware/omi}" \
  --token "${GITHUB_TOKEN:-}" --output "$ANDROID_ADMISSION_PROOF"
python3 "$ANDROID_ADMISSION_ROOT/.github/scripts/verify_mobile_release_admission.py" \
  --platform android --sha "$ANDROID_ADMISSION_SOURCE" \
  --repository "${GITHUB_REPOSITORY:-BasedHardware/omi}" \
  --proof "$ANDROID_ADMISSION_PROOF"
