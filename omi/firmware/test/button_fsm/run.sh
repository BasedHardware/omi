#!/usr/bin/env bash
# Host simulation of the firmware button tap FSM for both builds. Usage: ./run.sh
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
fw="$here/../.."
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
status=0
for src in "$fw/omi/src/lib/core/button.c" "$fw/devkit/src/button.c"; do
    echo "== ${src#$fw/}"
    # Extract from the BUTTON_PRESSED define through the end of check_button_level's body
    # (stops before the k_work_reschedule line; harness.c supplies the closing brace).
    sed -n '/^#define BUTTON_PRESSED 1/,/^    k_work_reschedule(&button_work/p' "$src" | sed '$d' >"$tmp/fsm_extracted.inc"
    gcc -std=c11 -Wall -Wno-unused-function -Wno-unused-variable -I"$tmp" "$here/harness.c" -o "$tmp/sim"
    "$tmp/sim" || status=1
done
exit $status
