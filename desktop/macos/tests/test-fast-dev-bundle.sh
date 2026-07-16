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

test "$(omi_fast_bundle_eligibility_reason "$TMP_ROOT/missing.app" "$stamp" "$agent_changed")" = "no_installed_bundle"
mkdir -p "$TMP_ROOT/installed.app/Contents"
test "$(omi_fast_bundle_eligibility_reason "$TMP_ROOT/installed.app" "$TMP_ROOT/missing.stamp" "$agent_changed")" = "missing_fast_fingerprint"
test "$(omi_fast_bundle_eligibility_reason "$TMP_ROOT/installed.app" "$stamp" "$first")" = "fast_fingerprint_mismatch"
test "$(omi_fast_bundle_eligibility_reason "$TMP_ROOT/installed.app" "$stamp" "$agent_changed")" = "reusable"

# An agent's failed --fast-only probe must not tear down a running app, clean
# build output, or start services merely to discover that the named bundle does
# not exist. Exercise the real launcher with a unique missing app name.
fast_only_output="$TMP_ROOT/fast-only-launcher.log"
fast_only_name="omi-fast-only-contract-$$"
if HOME="$TMP_ROOT/home" OMI_APP_NAME="$fast_only_name" "$MACOS_DIR/run.sh" --yolo --fast-only >"$fast_only_output" 2>&1; then
  echo "--fast-only unexpectedly succeeded for a missing bundle" >&2
  exit 1
else
  fast_only_status=$?
fi
test "$fast_only_status" = "3"
grep -q 'launch_mode=failed fast_reason=no_installed_bundle' "$fast_only_output"
if grep -qE 'Killing existing instances|Cleaning up conflicting app bundles|Starting Cloudflare|Starting Rust backend|Preparing agent runtime' "$fast_only_output"; then
  echo "--fast-only performed launch side effects before rejecting a missing bundle" >&2
  exit 1
fi

echo "fast-dev-bundle fingerprint tests passed"
