import XCTest

@testable import Omi_Computer

/// Ambient listening stopped on its own and stayed stopped, on hardware the user still had
/// plugged in. Reconfiguration retried three times at 1s, 2s and 3s and then cleared
/// `isCapturing` permanently — six seconds of patience for a device that had merely been
/// taken by another audio application. Aggregate and virtual inputs renegotiate their
/// stream format while something else holds them, and each renegotiation fires the format
/// listener, so the budget has to outlast the other app rather than the hardware.
final class AudioReconfigurationRetryPolicyTests: XCTestCase {
  private func delay(_ retryCount: Int, elapsed: TimeInterval) -> TimeInterval? {
    AudioCaptureService.reconfigurationRetryDelay(retryCount: retryCount, elapsed: elapsed)
  }

  func testKeepsTryingWellPastTheOldSixSecondBudget() {
    XCTAssertNotNil(
      delay(3, elapsed: 6),
      "six seconds is where the shipped policy gave up; a busy device is often not back yet")
    XCTAssertNotNil(delay(8, elapsed: 60), "a minute in, a device may still be held elsewhere")
    XCTAssertNotNil(delay(20, elapsed: 299), "the window is spent only at its end")
  }

  func testConcedesOnceTheWindowIsSpent() {
    XCTAssertNil(
      delay(20, elapsed: 300),
      "a device that never returns must still end in a bounded give-up, not a spin")
    XCTAssertNil(delay(0, elapsed: 3_600))
  }

  /// Backoff has to climb — retrying every second for five minutes would hammer CoreAudio
  /// through exactly the churn that triggered this — but it must also stop climbing, or the
  /// last attempts land minutes apart and the device is back long before Omi notices.
  func testBackoffClimbsToACeilingAndStaysThere() {
    XCTAssertEqual(delay(0, elapsed: 0), 1)
    XCTAssertEqual(delay(1, elapsed: 1), 2)
    XCTAssertEqual(delay(2, elapsed: 3), 4)
    XCTAssertEqual(delay(5, elapsed: 30), 30, "climbing is capped")
    XCTAssertEqual(delay(40, elapsed: 120), 30, "and stays capped rather than overflowing")
  }

  /// `reconfigureAfterChange` passes whatever attempt number it is on; a negative or absurd
  /// value must not produce a negative delay, which would schedule work in the past.
  func testDelayIsNeverNegative() {
    for retry in [-5, -1, 0, 7, 99] {
      let value = delay(retry, elapsed: 0)
      XCTAssertNotNil(value)
      XCTAssertGreaterThan(value ?? -1, 0, "a delay of \(retry) must still be a real wait")
    }
  }
}
