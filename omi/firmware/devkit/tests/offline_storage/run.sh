#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
test_dir="$repo_root/omi/firmware/devkit/tests/offline_storage"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/omi-devkit-storage-test.XXXXXX")"
trap 'rm -rf -- "$build_dir"' EXIT

"${CC:-cc}" \
  -std=c11 \
  -Wall \
  -Wextra \
  -Werror \
  -I"$test_dir/stubs" \
  -I"$repo_root/omi/firmware/devkit/src" \
  "$repo_root/omi/firmware/devkit/src/startup.c" \
  "$test_dir/test_startup.c" \
  -o "$build_dir/test_startup"

"$build_dir/test_startup"
