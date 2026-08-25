#!/usr/bin/env bash
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cc_bin="${CC:-cc}"

if ! command -v "$cc_bin" >/dev/null 2>&1; then
    echo "run_button_gesture_test: no C compiler ($cc_bin) available" >&2
    exit 1
fi

out="$(mktemp -d)"
trap 'rm -rf "$out"' EXIT

"$cc_bin" -std=c11 -Wall -Wextra -Werror -o "$out/test_button_gesture" "$here/test_button_gesture.c"
"$out/test_button_gesture"
