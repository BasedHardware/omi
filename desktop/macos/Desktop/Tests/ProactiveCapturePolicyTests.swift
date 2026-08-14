import XCTest

@testable import Omi_Computer

/// Regression coverage for `ProactiveCapturePolicy.captureTickAllowed`.
///
/// `stopMonitoring` used to leave `isInRecoveryMode` / `isInBackgroundPolling`
/// stuck true (and orphan the 60s background-poll timer) when a stop happened
/// mid-recovery. Because scheduled capture ticks are gated by exactly this
/// policy, a subsequent start then silently skipped every tick — monitoring
/// appeared on but never captured. These tests pin the gating contract that
/// makes clearing those flags on stop necessary and correct.
final class ProactiveCapturePolicyTests: XCTestCase {
  func testCaptureAllowedOnlyWhenMonitoringAndNotRecoveringOrPolling() {
    XCTAssertTrue(
      ProactiveCapturePolicy.captureTickAllowed(
        isMonitoring: true, isInRecoveryMode: false, isInBackgroundPolling: false))
  }

  func testStuckRecoveryFlagGatesCapture() {
    XCTAssertFalse(
      ProactiveCapturePolicy.captureTickAllowed(
        isMonitoring: true, isInRecoveryMode: true, isInBackgroundPolling: false),
      "A recovery flag left true after stop must not silently gate a restarted capture loop")
  }

  func testStuckBackgroundPollingFlagGatesCapture() {
    XCTAssertFalse(
      ProactiveCapturePolicy.captureTickAllowed(
        isMonitoring: true, isInRecoveryMode: false, isInBackgroundPolling: true))
  }

  func testNotMonitoringNeverCaptures() {
    XCTAssertFalse(
      ProactiveCapturePolicy.captureTickAllowed(
        isMonitoring: false, isInRecoveryMode: false, isInBackgroundPolling: false))
  }
}
