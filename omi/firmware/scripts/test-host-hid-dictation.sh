#!/usr/bin/env bash
# Host tests: pure protocol plus production runtime glue with mocked Zephyr/NCS I/O.
set -euo pipefail

FW_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/omi-hid-tests.XXXXXX")"
trap 'rm -rf "$OUT_DIR"' EXIT
OUT="$OUT_DIR/core"

CC="${CC:-cc}"
SRC="$FW_DIR/omi/src/lib/core/hid_dictation_core.c"
TEST="$FW_DIR/test/host/test_hid_dictation_core.c"

"$CC" -std=c11 -Wall -Wextra -Werror -O2 -o "$OUT" "$SRC" "$TEST"
"$OUT"

# Opt in to compiler sanitizers locally; the normal CI lane needs only a C compiler.
EXTRA=(-fno-omit-frame-pointer)
if [[ "${HID_SANITIZE:-0}" == 1 ]]; then
  EXTRA=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
# Header shims replace only OS/stack boundaries; the test includes production
# hid_dictation.c unchanged. These are deliberately not SDK compatibility tests.
for header in bluetooth/services/hids.h zephyr/bluetooth/{bluetooth,conn,gatt,uuid}.h zephyr/kernel.h zephyr/logging/log.h zephyr/settings/settings.h; do
  mkdir -p "$OUT_DIR/include/$(dirname "$header")"
  touch "$OUT_DIR/include/$header"
done
"$CC" -std=c11 -Wall -Wextra -Werror -Wno-unused-parameter -O1 -g \
  "${EXTRA[@]}" -I"$OUT_DIR/include" -o "$OUT_DIR/runtime" \
  "$SRC" "$FW_DIR/test/host/test_hid_dictation_runtime.c"
"$OUT_DIR/runtime"
if [[ "${HID_SANITIZE:-0}" == 1 ]]; then
  "$CC" -std=c11 -Wall -Wextra -Werror -O1 -g "${EXTRA[@]}" -o "$OUT_DIR/core-sanitized" "$SRC" "$TEST"
  "$OUT_DIR/core-sanitized"
fi
