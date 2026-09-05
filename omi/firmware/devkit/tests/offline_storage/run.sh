#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
test_dir="$repo_root/omi/firmware/devkit/tests/offline_storage"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/omi-devkit-storage-test.XXXXXX")"
trap 'rm -rf -- "$build_dir"' EXIT

cc="${CC:-}"
if [ -z "$cc" ]; then
    for candidate in cc gcc clang; do
        if command -v "$candidate" >/dev/null 2>&1; then
            cc="$candidate"
            break
        fi
    done
fi
if [ -z "$cc" ]; then
    echo "error: no C compiler found (looked for cc, gcc, clang; set \$CC to override)" >&2
    exit 1
fi

"$cc" \
  -std=c11 \
  -Wall \
  -Wextra \
  -Wno-strict-prototypes \
  -Werror \
  -I"$test_dir/stubs" \
  -I"$repo_root/omi/firmware/devkit/src" \
  "$repo_root/omi/firmware/devkit/src/startup.c" \
  "$test_dir/test_startup.c" \
  -o "$build_dir/test_startup"

"$build_dir/test_startup"
