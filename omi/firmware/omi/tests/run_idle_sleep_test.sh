#!/usr/bin/env bash
# Host-runnable test for the Zephyr-free idle auto-sleep policy.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cc="${CC:-cc}"
out="$(mktemp -d)"
trap 'rm -rf "$out"' EXIT

"$cc" -std=c11 -Wall -Wextra -Werror -o "$out/test_idle_sleep" "$script_dir/test_idle_sleep.c"
"$out/test_idle_sleep"
