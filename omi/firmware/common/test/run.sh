#!/usr/bin/env bash
# Host-compiles and runs the shared firmware button gesture test.
# Registered as `firmware-button-gesture-tests` in .github/checks-manifest.yaml.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMON="$(dirname "$HERE")"
OUT="$(mktemp -d)"
trap 'rm -rf "$OUT"' EXIT

CC="${CC:-cc}"
"$CC" -std=c11 -Wall -Wextra -Werror -pedantic -I"$COMMON" \
  "$COMMON/button_gesture.c" "$HERE/button_gesture_test.c" -o "$OUT/button_gesture_test"
"$OUT/button_gesture_test"
