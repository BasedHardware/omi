#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=../scripts/launcher-bootstrap.sh
source "$MACOS_DIR/scripts/launcher-bootstrap.sh"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/omi-launcher-bootstrap.XXXXXX")"
cleanup() {
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

ARM_PREFIX="$TMP_ROOT/opt/homebrew"
INTEL_PREFIX="$TMP_ROOT/usr/local"
ORIGINAL_PATH="$PATH"
mkdir -p "$ARM_PREFIX/bin" "$INTEL_PREFIX/bin" "$TMP_ROOT/system/bin"

assert_path_order() {
  local architecture="$1"
  local expected_native="$2"
  local expected_fallback="$3"
  local -a path_entries

  PATH="$expected_fallback:$TMP_ROOT/system/bin:$expected_native:$ORIGINAL_PATH"
  omi_configure_homebrew_path "$architecture" "$ARM_PREFIX" "$INTEL_PREFIX"
  IFS=: read -r -a path_entries <<< "$PATH"

  [ "${path_entries[0]}" = "$expected_native" ] \
    || fail "$architecture should prefer native Homebrew: $PATH"
  [ "${path_entries[1]}" = "$expected_fallback" ] \
    || fail "$architecture should keep fallback Homebrew second: $PATH"

  local entry count=0
  for entry in "${path_entries[@]}"; do
    [ "$entry" = "$expected_native" ] && count=$((count + 1))
  done
  [ "$count" = 1 ] || fail "$architecture duplicated native Homebrew: $PATH"
}

assert_path_order arm64 "$ARM_PREFIX/bin" "$INTEL_PREFIX/bin"
assert_path_order x86_64 "$INTEL_PREFIX/bin" "$ARM_PREFIX/bin"

RESOURCE_BUNDLE="$TMP_ROOT/Omi Computer_Omi Computer.bundle"
ROOT_NODE="$RESOURCE_BUNDLE/node"
NESTED_NODE="$RESOURCE_BUNDLE/Contents/Resources/node"
mkdir -p "$RESOURCE_BUNDLE"
printf '#!/bin/sh\nexit 0\n' > "$ROOT_NODE"
chmod +x "$ROOT_NODE"

omi_normalize_packaged_resource_bundle "$RESOURCE_BUNDLE"
[ ! -e "$ROOT_NODE" ] || fail "root-level Node executable was not moved"
[ -x "$NESTED_NODE" ] || fail "Node executable was not placed in nested resources"

# An already-normalized bundle must remain unchanged.
printf 'nested-node\n' > "$NESTED_NODE"
printf 'root-node\n' > "$ROOT_NODE"
omi_normalize_packaged_resource_bundle "$RESOURCE_BUNDLE"
grep -Fxq 'nested-node' "$NESTED_NODE" \
  || fail "existing nested Node executable was overwritten"
[ -f "$ROOT_NODE" ] || fail "root Node should remain when nested Node already exists"

omi_normalize_packaged_resource_bundle "$TMP_ROOT/missing.bundle"

echo "launcher bootstrap tests passed"
