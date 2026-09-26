#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
SRC="$(cd "$(dirname "$0")" && pwd)/tap_sequence_test.c"
OUT="$(mktemp)"
trap 'rm -f "$OUT"' EXIT
gcc -std=c11 -Wall -Wextra -Werror -pedantic -I"$ROOT/common" -o "$OUT" "$SRC"
"$OUT"
