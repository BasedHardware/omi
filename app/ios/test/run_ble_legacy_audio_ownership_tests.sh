#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ownership_test_binary="$(mktemp "${TMPDIR:-/tmp}/ble-legacy-audio-ownership.XXXXXX")"
connection_test_binary="$(mktemp "${TMPDIR:-/tmp}/ble-known-peripheral-connection.XXXXXX")"
trap 'rm -f "$ownership_test_binary" "$connection_test_binary"' EXIT

xcrun swiftc \
  "$repo_root/app/ios/Runner/Ble/BleLegacyAudioOwnership.swift" \
  "$repo_root/app/ios/test/BleLegacyAudioOwnershipTests.swift" \
  -o "$ownership_test_binary"

"$ownership_test_binary"

xcrun swiftc \
  "$repo_root/app/ios/Runner/Ble/BleKnownPeripheralConnectionPolicy.swift" \
  "$repo_root/app/ios/test/BleKnownPeripheralConnectionPolicyTests.swift" \
  -o "$connection_test_binary"

"$connection_test_binary"
