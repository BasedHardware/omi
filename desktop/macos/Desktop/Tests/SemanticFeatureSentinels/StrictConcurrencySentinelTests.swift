import XCTest

/// Sentinel: proves strict concurrency is active on this target.
///
/// History: under Swift 5, this sentinel relied on a non-Sendable
/// `Task.detached` capture producing a *warning* when
/// `-strict-concurrency=complete` was set (this target has no
/// `-warnings-as-errors`, so it still compiled). The companion shell test
/// (`test-feature-sentinel-negative-control.sh`) rebuilt the target and grepped
/// the build output for that warning — if the flag was silently removed, the
/// warning vanished and the test failed.
///
/// Under the Swift 6 language mode that same non-Sendable capture is a *hard
/// compile error*: strict concurrency is no longer opt-in via a flag but
/// inherent to the language mode itself. This file therefore cannot contain the
/// unsafe capture and still compile — its compilation under
/// `swiftLanguageMode(.v6)` is itself the proof that strict concurrency is
/// enforced. The companion shell test now asserts the inverse: a deliberately
/// unsafe capture is *rejected* by the compiler.
final class StrictConcurrencySentinelTests: XCTestCase {
  /// A type that is NOT Sendable (no @unchecked Sendable).
  final class NonSendableBox {
    var value: Int = 0
  }

  /// Exercises the compiler-approved pattern for Swift 6 strict concurrency:
  /// copy the Sendable value out before crossing a concurrency boundary.
  func testSendableValueCrossesTaskBoundarySafely() {
    let box = NonSendableBox()
    box.value = 42
    // `box` is non-Sendable and may NOT be captured across the boundary.
    // Copying the Sendable `Int` out first is the pattern the compiler now
    // requires; attempting to capture `box` directly is a compile error.
    let snapshot = box.value
    Task.detached { _ = snapshot }
    XCTAssertEqual(snapshot, 42)
  }
}
