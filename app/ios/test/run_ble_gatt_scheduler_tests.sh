#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/omi-ble-gatt-tests.XXXXXX")"
trap 'rm -rf -- "$build_dir"' EXIT

swift_compiler=(swiftc)
if [[ "$(uname -s)" == "Darwin" ]]; then
  swift_compiler=(xcrun --sdk macosx swiftc)
fi

"${swift_compiler[@]}" \
  "$repo_root/app/ios/Runner/Ble/BleGattOperationScheduler.swift" \
  "$repo_root/app/ios/test/BleGattOperationSchedulerTests.swift" \
  -o "$build_dir/BleGattOperationSchedulerTests"

"$build_dir/BleGattOperationSchedulerTests"

"${swift_compiler[@]}" \
  "$repo_root/app/ios/Runner/Ble/BleNotificationRouter.swift" \
  "$repo_root/app/ios/test/BleNotificationRouterTests.swift" \
  -o "$build_dir/BleNotificationRouterTests"

"$build_dir/BleNotificationRouterTests"

ruby "$repo_root/app/ios/test/ble_gatt_project_graph_test.rb"

if [[ "$(uname -s)" == "Darwin" ]]; then
  xcodebuild -list -project "$repo_root/app/ios/Runner.xcodeproj" >/dev/null
fi

if [[ "$(uname -s)" == "Darwin" ]] && flutter_bin="$(command -v flutter)"; then
  flutter_bin="$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$flutter_bin")"
  flutter_root="$(cd "$(dirname "$flutter_bin")/.." && pwd)"
  ios_sdk="$(xcrun --sdk iphoneos --show-sdk-path)"
  flutter_frameworks="$flutter_root/bin/cache/artifacts/engine/ios/Flutter.xcframework/ios-arm64"
  xcrun swiftc \
    -typecheck \
    -parse-as-library \
    -sdk "$ios_sdk" \
    -target arm64-apple-ios15.0 \
    -F "$flutter_frameworks" \
    "$repo_root/app/ios/Runner/Ble/BleGattOperationScheduler.swift" \
    "$repo_root/app/ios/Runner/Ble/BleNotificationRouter.swift" \
    "$repo_root/app/ios/Runner/PigeonCommunicator.g.swift" \
    "$repo_root/app/ios/Runner/Ble/OmiBleManager.swift" \
    "$repo_root/app/ios/test/BleManagerDependencyTypecheckStubs.swift"
else
  echo "Flutter SDK unavailable; skipped OmiBleManager iOS typecheck"
fi
