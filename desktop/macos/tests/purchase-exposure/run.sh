#!/bin/bash
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/omi-purchase-exposure.XXXXXX")"
trap 'rm -f "$work/test" "$work/coordinator-test" "$work/OmiTheme.swiftmodule" "$work/OmiTheme.swiftdoc" "$work/OmiTheme.swiftsourceinfo" "$work/OmiTheme.abi.json"; rmdir "$work"' EXIT
xcrun swiftc "$root/Desktop/Sources/Generated/PurchaseContract.generated.swift" \
  "$root/Desktop/Sources/MainWindow/Pages/Settings/Components/PurchaseTelemetry.swift" \
  "$root/tests/purchase-exposure/main.swift" -o "$work/test"
"$work/test"

xcrun swiftc -target arm64-apple-macosx14.0 -emit-module -module-name OmiTheme "$root/tests/purchase-exposure/ThemeModule.swift" -emit-module-path "$work/OmiTheme.swiftmodule"
xcrun swiftc -parse-as-library -target arm64-apple-macosx14.0 -I "$work" \
  "$root/Desktop/Sources/Generated/PurchaseContract.generated.swift" \
  "$root/Desktop/Sources/MainWindow/Pages/Settings/Components/PurchaseTelemetry.swift" \
  "$root/Desktop/Sources/MainWindow/Pages/Settings/Components/PurchaseExposureModifier.swift" \
  "$root/Desktop/Sources/MainWindow/Pages/Settings/Components/BillingWebFlow.swift" \
  "$root/Desktop/Sources/UsageLimitPopupView.swift" \
  "$root/tests/purchase-exposure/ThemeStubs.swift" "$root/tests/purchase-exposure/CoordinatorTests.swift" -o "$work/coordinator-test"
"$work/coordinator-test"
