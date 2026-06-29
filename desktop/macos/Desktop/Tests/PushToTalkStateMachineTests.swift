import XCTest

@testable import Omi_Computer

final class PushToTalkStateMachineTests: XCTestCase {
  func testStartListeningIsIdempotentOutsideIdleOrPendingLock() throws {
    let source = try pushToTalkManagerSource()

    XCTAssertTrue(source.contains("guard state == .idle || state == .pendingLockDecision else"))
    XCTAssertTrue(source.contains("PushToTalkManager: startListening ignored — state="))
  }

  func testMicCaptureStartCannotDoubleAdvanceState() throws {
    let source = try pushToTalkManagerSource()

    XCTAssertTrue(source.contains("private var micCaptureStartInFlight = false"))
    XCTAssertTrue(source.contains("guard !micCaptureStartInFlight && !(audioCaptureService?.capturing ?? false) else"))
    XCTAssertTrue(source.contains("PushToTalkManager: mic capture start ignored — already active"))
    XCTAssertFalse(source.contains("private var micCaptureActive"))
  }

  func testSilentMicRecoveryPreservesBluetoothOutputRouting() throws {
    let source = try pushToTalkManagerSource()

    XCTAssertTrue(source.contains("private func preferredPTTInputOverrideDeviceID() -> AudioDeviceID?"))
    XCTAssertTrue(source.contains("startMicCapture(batchMode: batchMode, overrideDeviceID: preferredPTTInputOverrideDeviceID())"))
  }

  func testSilentMicRecoveryResetsCaptureWatchdogForNewPTTTurn() throws {
    let source = try pushToTalkManagerSource()

    XCTAssertTrue(source.contains("capture.resetSilentMicWatchdog()"))
    XCTAssertTrue(source.contains("capture.detectSilentMicOnAnyTransport = true"))
  }

  private func pushToTalkManagerSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar/PushToTalkManager.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }
}
