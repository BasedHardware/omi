#!/usr/bin/env bash
# Compiles and runs the host-side device-name policy tests (no Zephyr toolchain needed).
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
out="$(mktemp -d)"
trap 'rm -rf "$out"' EXIT

cc="${CC:-cc}"
"$cc" -std=c11 -Wall -Wextra -Werror -o "$out/test_device_name" "$here/test_device_name.c"
"$out/test_device_name"
