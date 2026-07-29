import XCTest

@testable import Omi_Computer

/// Contract for `SecureInputCaptureGate`: while macOS reports secure keyboard entry, the
/// capture tick must skip, and it must keep skipping through a short backoff after the flag
/// clears so a credential still on screen is not imaged by the next tick.
///
/// A flag an app never clears must not silently pause capture forever — the gate still
/// skips, but reports exactly once per continuous run so the pause is observable.
final class SecureInputCaptureGateTests: XCTestCase {
  private let backoff: TimeInterval = 2
  private let stuckThreshold: TimeInterval = 300
  private let start = Date(timeIntervalSince1970: 1_700_000_000)

  func testSecureInputActiveSkipsCapture() {
    var gate = SecureInputCaptureGate()
    XCTAssertEqual(
      gate.nextDecision(
        isSecureInputActive: true, now: start, backoffDuration: backoff,
        stuckThreshold: stuckThreshold),
      .skip(reportStuck: false),
      "A focused password field must never be captured")
  }

  func testIdleStateCaptures() {
    var gate = SecureInputCaptureGate()
    XCTAssertEqual(
      gate.nextDecision(
        isSecureInputActive: false, now: start, backoffDuration: backoff,
        stuckThreshold: stuckThreshold),
      .capture)
  }

  func testClearedFlagStillSkipsInsideBackoff() {
    var gate = SecureInputCaptureGate()
    _ = gate.nextDecision(
      isSecureInputActive: true, now: start, backoffDuration: backoff,
      stuckThreshold: stuckThreshold)

    XCTAssertEqual(
      gate.nextDecision(
        isSecureInputActive: false, now: start.addingTimeInterval(1), backoffDuration: backoff,
        stuckThreshold: stuckThreshold),
      .skip(reportStuck: false),
      "A revealed or filled credential can outlive the flag by a frame")
  }

  func testCaptureResumesAfterBackoff() {
    var gate = SecureInputCaptureGate()
    _ = gate.nextDecision(
      isSecureInputActive: true, now: start, backoffDuration: backoff,
      stuckThreshold: stuckThreshold)

    XCTAssertEqual(
      gate.nextDecision(
        isSecureInputActive: false, now: start.addingTimeInterval(backoff + 1),
        backoffDuration: backoff, stuckThreshold: stuckThreshold),
      .capture,
      "Capture must resume on its own; the gate is not a latch")
  }

  func testStuckFlagReportsOnceAndKeepsSkipping() {
    var gate = SecureInputCaptureGate()
    _ = gate.nextDecision(
      isSecureInputActive: true, now: start, backoffDuration: backoff,
      stuckThreshold: stuckThreshold)

    XCTAssertEqual(
      gate.nextDecision(
        isSecureInputActive: true, now: start.addingTimeInterval(stuckThreshold),
        backoffDuration: backoff, stuckThreshold: stuckThreshold),
      .skip(reportStuck: true))

    XCTAssertEqual(
      gate.nextDecision(
        isSecureInputActive: true, now: start.addingTimeInterval(stuckThreshold * 2),
        backoffDuration: backoff, stuckThreshold: stuckThreshold),
      .skip(reportStuck: false),
      "A stuck flag must cost one telemetry event per run, not one per tick")
  }

  func testStuckReportArmsAgainForALaterRun() {
    var gate = SecureInputCaptureGate()
    _ = gate.nextDecision(
      isSecureInputActive: true, now: start, backoffDuration: backoff,
      stuckThreshold: stuckThreshold)
    _ = gate.nextDecision(
      isSecureInputActive: true, now: start.addingTimeInterval(stuckThreshold),
      backoffDuration: backoff, stuckThreshold: stuckThreshold)

    let cleared = start.addingTimeInterval(stuckThreshold + backoff + 1)
    XCTAssertEqual(
      gate.nextDecision(
        isSecureInputActive: false, now: cleared, backoffDuration: backoff,
        stuckThreshold: stuckThreshold),
      .capture)

    _ = gate.nextDecision(
      isSecureInputActive: true, now: cleared, backoffDuration: backoff,
      stuckThreshold: stuckThreshold)
    XCTAssertEqual(
      gate.nextDecision(
        isSecureInputActive: true, now: cleared.addingTimeInterval(stuckThreshold),
        backoffDuration: backoff, stuckThreshold: stuckThreshold),
      .skip(reportStuck: true),
      "A second stuck run is a new incident and must be reported")
  }

  func testResetClearsBackoffAndStuckState() {
    var gate = SecureInputCaptureGate()
    _ = gate.nextDecision(
      isSecureInputActive: true, now: start, backoffDuration: backoff,
      stuckThreshold: stuckThreshold)

    gate.reset()

    XCTAssertEqual(
      gate.nextDecision(
        isSecureInputActive: false, now: start, backoffDuration: backoff,
        stuckThreshold: stuckThreshold),
      .capture,
      "stopMonitoring must not leave a backoff that gates the next start")
  }
}
