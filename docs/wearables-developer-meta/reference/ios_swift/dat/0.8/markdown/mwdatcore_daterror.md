---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_daterror
title: DatError Protocol
scraped_at: 2026-07-03T14:24:18.306Z
---

# DatError Protocol
Extends
Error, Sendable, LocalizedError
Base protocol for all DAT SDK error types.
All public error types in the SDK should conform to this protocol, providing a consistent contract for error handling and analytics.
Conforming types **must** implement [description](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_daterror#description) to provide a human-readable error message. This is enforced at compile time — the compiler will emit an error if a conforming type does not provide it.
> Important: Conforming types **must not** also adopt > `CustomStringConvertible`. The SDK uses runtime reflection (via > `String(describing:)`) on enum cases without associated values to > extract the case name for analytics. Adopting `CustomStringConvertible` > would cause `String(describing:)` to return the custom description > (e.g. `"Operation timed out"`) instead of the case name (e.g. `"timeout"`), > silently producing incorrect analytics. The `description` requirement on > this protocol already provides the same human-readable message without > breaking case name extraction, so a separate `CustomStringConvertible` > conformance is unnecessary.
## Example
```swift
public enum MyError: DatError, Equatable { case somethingFailed public var description: String { switch self { case .somethingFailed: return "Something failed" } } }
```
## Signature
```swift
protocol DatError: Error, Sendable, LocalizedError
```
## Properties
description
: String
[Get]
|
A human-readable description of the error suitable for logging, debugging, and display to developers. This should return the English version of the error.
|
