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
    XCTAssertTrue(source.contains("private var micCaptureGeneration: UInt64 = 0"))
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

  func testLateMicCaptureStartParksWarmInsteadOfLeakingIntoIdlePTT() throws {
    let source = try pushToTalkManagerSource()

    XCTAssertTrue(source.contains("let generation = micCaptureGeneration"))
    XCTAssertTrue(source.contains("guard self.micCaptureGeneration == generation, self.shouldKeepMicCaptureAlive else { return }"))
    XCTAssertTrue(source.contains("self.parkMicCapture(capture, lease: lease, overrideID: overrideDeviceID)"))
    XCTAssertTrue(source.contains("self.audioCaptureService === capture"))
    XCTAssertTrue(source.contains("PushToTalkManager: mic capture start completed after turn ended — parked warm"))
    XCTAssertTrue(source.contains("guard self.micCaptureGeneration == generation else {"))
  }

  func testWarmMicReuseRestoresLeaseAndCancelDiscardsParking() throws {
    let source = try pushToTalkManagerSource()

    XCTAssertTrue(source.contains("activeMicLease = parked.lease"))
    XCTAssertTrue(source.contains("activeMicOverrideID = overrideDeviceID"))
    XCTAssertTrue(source.contains("stopAudioTranscription(parkWarm: false)"))
    XCTAssertTrue(source.contains("private func stopAudioTranscription(parkWarm: Bool = true)"))
  }

  func testPTTContentionIgnoresManagersOwnParkedCapture() throws {
    let source = try pushToTalkManagerSource()

    XCTAssertTrue(source.contains("let parkedCapture = parkedMicCapture?.service"))
    XCTAssertTrue(source.contains("isDeviceActivelyCaptured(defaultInput, excluding: parkedCapture)"))
    XCTAssertTrue(source.contains("hasActiveCapture(excluding: parkedCapture)"))
  }

  private func pushToTalkManagerSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar/PushToTalkManager.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }
}
