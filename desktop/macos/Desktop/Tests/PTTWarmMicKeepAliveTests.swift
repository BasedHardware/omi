import XCTest

@testable import Omi_Computer

/// Static contracts for the PTT warm mic keep-alive and mic-contention routing
/// introduced with the Ray-Ban Meta microphone picker. These are labeled
/// source-inspection tripwires, not behavioral coverage: the guarded behavior
/// (CoreAudio IOProc reuse and cross-capture device contention) needs real
/// audio hardware, so the contract asserts the load-bearing code paths exist.
final class PTTWarmMicKeepAliveTests: XCTestCase {

  func testLateMicCaptureStartParksWarmInsteadOfLeakingIntoIdlePTT() throws {
    let source = try pushToTalkManagerSource()

    XCTAssertTrue(source.contains("let generation = micCaptureGeneration"))
    XCTAssertTrue(source.contains("self.parkMicCapture(capture, lease: lease, overrideID: overrideDeviceID)"))
    XCTAssertTrue(source.contains("self.audioCaptureService === capture"))
    XCTAssertTrue(source.contains("PushToTalkManager: mic capture start completed after turn ended — parked warm"))
    XCTAssertTrue(
      source.contains("voiceTurnCoordinator.publish(.captureStarted(turnID: turnID, captureID: captureID))"))
  }

  func testWarmMicReuseRestoresLeaseAndTerminalCleanupDiscardsParking() throws {
    let source = try pushToTalkManagerSource()

    XCTAssertTrue(source.contains("activeMicLease = parked.lease"))
    XCTAssertTrue(source.contains("activeMicOverrideID = overrideDeviceID"))
    // Terminal cleanup must fully release the mic — no warm capture may outlive
    // a turn the user explicitly ended.
    XCTAssertTrue(source.contains("parkWarm: false)"))
    XCTAssertTrue(
      source.contains("private func stopAudioTranscription(discardBufferedAudio: Bool = false, parkWarm: Bool = true)"))
  }

  func testPTTContentionIgnoresManagersOwnParkedCapture() throws {
    let source = try inputDeviceRoutingSource()

    XCTAssertTrue(source.contains("let parkedCapture = parkedMicCapture?.service"))
    XCTAssertTrue(source.contains("isDeviceActivelyCaptured(defaultInput, excluding: parkedCapture)"))
    XCTAssertTrue(source.contains("hasActiveCapture(excluding: parkedCapture)"))
  }

  func testMicrophonePickerUsesDeviceListenerInsteadOfPolling() throws {
    let sourceURL = sourcesRoot()
      .appendingPathComponent("MainWindow/Pages/Settings/Sections/MicrophonePickerCard.swift")
    // omi-test-quality: source-inspection -- static contract: settings listens for CoreAudio device changes
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertTrue(source.contains("AudioObjectAddPropertyListenerBlock"))
    XCTAssertTrue(source.contains("kAudioHardwarePropertyDevices"))
    XCTAssertTrue(source.contains(".task(id: deviceListObserver.revision)"))
    XCTAssertFalse(source.contains("refreshDevicesPeriodically"))
    XCTAssertFalse(source.contains("Task.sleep"))
  }

  func testSeedStaleReconnectDefersUntilTurnCompletion() throws {
    let controllerURL = sourcesRoot()
      .appendingPathComponent("FloatingControlBar/RealtimeHubController.swift")
    let lifecycleURL = sourcesRoot()
      .appendingPathComponent("FloatingControlBar/RealtimeHubController+SessionLifecycle.swift")
    // omi-test-quality: source-inspection -- static contract: seed-stale refresh defers past an in-flight turn
    let controller = try String(contentsOf: controllerURL, encoding: .utf8)
    // omi-test-quality: source-inspection -- static contract: turn completion drains the deferred refresh
    let lifecycle = try String(contentsOf: lifecycleURL, encoding: .utf8)

    XCTAssertTrue(controller.contains("pendingSessionRefreshReason = reason"))
    XCTAssertTrue(controller.contains("func applyPendingSessionRefreshIfIdle()"))
    XCTAssertTrue(
      lifecycle.contains("if pendingSessionRefreshReason != nil { applyPendingSessionRefreshIfIdle() }"),
      "turn completion must drain a deferred voice-seed refresh instead of dropping it")
  }

  private func sourcesRoot() -> URL {
    URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")
  }

  private func pushToTalkManagerSource() throws -> String {
    // omi-test-quality: source-inspection -- static contract: PTT parks and reuses its warm mic capture
    try String(
      contentsOf: sourcesRoot().appendingPathComponent("FloatingControlBar/PushToTalkManager.swift"),
      encoding: .utf8)
  }

  private func inputDeviceRoutingSource() throws -> String {
    // omi-test-quality: source-inspection -- static contract: PTT routes around captures other components hold
    try String(
      contentsOf: sourcesRoot()
        .appendingPathComponent("FloatingControlBar/PushToTalkManager+InputDeviceRouting.swift"),
      encoding: .utf8)
  }
}
