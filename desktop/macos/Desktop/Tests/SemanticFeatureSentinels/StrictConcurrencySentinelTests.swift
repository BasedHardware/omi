import XCTest

/// Sentinel: proves `-strict-concurrency=complete` is active on this target.
///
/// Unlike BareSlashRegexLiterals (which enables new syntax), strict concurrency
/// only adds restrictions — there is no code that "only compiles" under it.
/// So we verify the flag two ways:
///
/// 1. This file captures a non-Sendable type across a Task.detached boundary.
///    Under complete checking, the compiler emits a "non-Sendable" / "data race"
///    warning. Under minimal checking, no warning is produced.
///
/// 2. The companion shell test (test-feature-sentinel-negative-control.sh)
///    rebuilds this target and greps the output for the non-Sendable warning.
///    If the flag is removed from Package.swift, the warning disappears and
///    the test fails — catching the "fake strictness" trap.
final class StrictConcurrencySentinelTests: XCTestCase {
  /// A type that is NOT Sendable (no @unchecked Sendable).
  final class NonSendableBox {
    var value: Int = 0
  }

  func testNonSendableCaptureIsFlaggedUnderCompleteChecking() {
    // Under -strict-concurrency=complete, capturing NonSendableBox in a
    // detached Task produces a warning about non-Sendable capture.
    // The code still compiles (we do NOT use -warnings-as-errors on this
    // target), but the warning is visible in the build output and proves
    // the flag is active.
    let box = NonSendableBox()
    box.value = 42

    // The capture below is intentional — it triggers the sentinel warning.
    Task.detached {
      _ = box.value
    }

    XCTAssertEqual(box.value, 42)
  }
}
