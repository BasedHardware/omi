#!/usr/bin/env bash
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
build_dir="$(mktemp -d)"
trap 'rm -rf "$build_dir"' EXIT
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror \
  -I "$here/settings_stubs" -I "$here/../src/lib/core" \
  "$here/test_capture_mute_settings.c" -o "$build_dir/capture-mute-test"
"$build_dir/capture-mute-test"
