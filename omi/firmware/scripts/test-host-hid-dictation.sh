#!/usr/bin/env bash
# Host-side unit tests for the pendant HID dictation protocol core.
# Compiles the pure protocol core (no Zephyr) and runs the test binary.
set -euo pipefail

FW_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${TMPDIR:-/tmp}/omi-hid-dictation-tests"

CC="${CC:-cc}"
SRC="$FW_DIR/omi/src/lib/core/hid_dictation_core.c"
TEST="$FW_DIR/test/host/test_hid_dictation_core.c"

"$CC" -std=c11 -Wall -Wextra -Werror -O2 -o "$OUT" "$SRC" "$TEST"
"$OUT"
