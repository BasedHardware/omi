#!/usr/bin/env bash
set -euo pipefail
TEST_ROOT=$(cd "$(dirname "$0")" && pwd)
TEST_BUILD=$(mktemp -d "${TMPDIR:-/tmp}/omi-firmware-host.XXXXXX")
trap 'rm -rf "$TEST_BUILD"' EXIT
for name in button_input sd_worker_wait; do
    "${CC:-cc}" -std=gnu11 -Wall -Wextra -Werror -g \
        -fsanitize=address,undefined -fno-omit-frame-pointer \
        -I "$TEST_ROOT/include" "$TEST_ROOT/test_$name.c" -o "$TEST_BUILD/test_$name"
    "$TEST_BUILD/test_$name"
done
