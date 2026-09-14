#!/usr/bin/env bash
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
out="$(mktemp -d)"
trap 'rm -rf "$out"' EXIT

cc -std=c99 -Wall -Wextra -Werror -iquote "$here/../../src/lib/core" "$here/tap_sequence_test.c" -o "$out/tap_sequence_test"
"$out/tap_sequence_test"
