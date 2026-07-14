#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$MACOS_DIR/scripts/fast-dev-bundle.sh"

TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/omi-fast-dev-bundle.XXXXXX")"
cleanup() {
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

make_file() {
  local path="$1"
  local contents="$2"
  mkdir -p "$(dirname "$TMP_ROOT/$path")"
  printf '%s\n' "$contents" > "$TMP_ROOT/$path"
}

make_file run.sh 'launcher'
make_file Desktop/Package.swift 'package'
make_file Desktop/Sources/Resources/asset.txt 'asset'
make_file agent/src/index.ts 'agent'
make_file agent/node_modules/ignored.txt 'first'
make_file pi-mono-extension/index.ts 'extension'

first="$(omi_fast_bundle_fingerprint "$TMP_ROOT" bundle development yolo)"
second="$(omi_fast_bundle_fingerprint "$TMP_ROOT" bundle development yolo)"
test "$first" = "$second"

# Agent preparation stages the Node executable during a full bootstrap. The
# persisted stamp must be based on this completed state, not the pre-stage one.
make_file Desktop/Sources/Resources/node 'node-v1'
with_staged_node="$(omi_fast_bundle_fingerprint "$TMP_ROOT" bundle development yolo)"
test "$first" != "$with_staged_node"

# Working dependency trees are not packaged inputs; agent source is.
make_file agent/node_modules/ignored.txt 'second'
test "$with_staged_node" = "$(omi_fast_bundle_fingerprint "$TMP_ROOT" bundle development yolo)"

make_file agent/src/index.ts 'agent changed'
agent_changed="$(omi_fast_bundle_fingerprint "$TMP_ROOT" bundle development yolo)"
test "$with_staged_node" != "$agent_changed"

test "$agent_changed" != "$(omi_fast_bundle_fingerprint "$TMP_ROOT" bundle adhoc yolo)"

stamp="$TMP_ROOT/.dev/fast-bundles/bundle.stamp"
! omi_fast_bundle_stamp_matches "$stamp" "$agent_changed"
omi_fast_bundle_write_stamp "$stamp" "$agent_changed"
omi_fast_bundle_stamp_matches "$stamp" "$agent_changed"
! omi_fast_bundle_stamp_matches "$stamp" "$first"

echo "fast-dev-bundle fingerprint tests passed"
