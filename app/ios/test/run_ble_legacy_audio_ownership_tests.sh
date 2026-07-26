#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
test_binary="$(mktemp "${TMPDIR:-/tmp}/ble-legacy-audio-ownership.XXXXXX")"
trap 'rm -f "$test_binary"' EXIT

xcrun swiftc \
  "$repo_root/app/ios/Runner/Ble/BleLegacyAudioOwnership.swift" \
  "$repo_root/app/ios/test/BleLegacyAudioOwnershipTests.swift" \
  -o "$test_binary"

"$test_binary"
