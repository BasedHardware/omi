#!/usr/bin/env bash
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
build_dir="$(mktemp -d)"
trap 'rm -rf "$build_dir"' EXIT
# Production headers resolve beside their source files. Adding core to -I
# would shadow glibc <features.h> with the firmware features.h on Linux.
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror \
  -I "$here/settings_stubs" \
  "$here/test_capture_mute_settings.c" -o "$build_dir/capture-mute-test"
"$build_dir/capture-mute-test"
