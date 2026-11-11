# Native Foundation sink safety

Use `SafeDefaults.set(_ value: PlistValue?, forKey:in:)` for scalar and structured property-list values. Passing nil removes the key; `.double` rejects NaN and infinity. For existing dictionary-array readers, use `SafeDefaults.setPlistRecords(_:forKey:in:)` with typed fields. For model arrays, use `SafeDefaults.setRecords(_:forKey:in:)` and `records(_:forKey:in:)`; they store Codable records as `Data` and reject non-finite fields before writing. A migration from legacy dictionary arrays must read the old property-list array and write a typed replacement while preserving reader compatibility.

Use `SafeJSON.data(withJSONObject:options:)` for any `JSONSerialization` write. It rejects unsupported values and non-finite numbers before calling the Objective-C serializer. Use `CheckedIntegerConversion.int(_:)` or `.int64(_:)` for floating-point conversions; nil means non-finite or out of range.

Run `bash app/ios/scripts/swiftlint-wrapper.sh lint` from the repository root. The committed baseline records existing violations; `python3 app/ios/scripts/check-swiftlint-baseline.py --base origin/main` rejects additions. Generated Pigeon Swift is outside this lint scope.

Xcode 27's `swiftc -help` exposes `-warnings-as-errors` for all warnings but no per-diagnostic promotion flag for the implicit Optional-to-Any warning. Enabling global warnings-as-errors for Runner would couple unrelated warnings to the build. The iOS SwiftLint rules and typed sink API enforce this boundary instead.
