import XCTest

@testable import Omi_Computer

final class PushToTalkStateMachineTests: XCTestCase {
  func testLegacyPublishedStateIsDerivedFromAuthoritativeVoiceTurnPhase() {
    XCTAssertEqual(PushToTalkManager.legacyState(for: nil), .idle)
    XCTAssertEqual(PushToTalkManager.legacyState(for: .idle), .idle)
    XCTAssertEqual(PushToTalkManager.legacyState(for: .recording), .listening)
    XCTAssertEqual(PushToTalkManager.legacyState(for: .pendingLockDecision), .pendingLockDecision)
    XCTAssertEqual(PushToTalkManager.legacyState(for: .lockedRecording), .lockedListening)
    XCTAssertEqual(PushToTalkManager.legacyState(for: .finalizing), .finalizing)
    XCTAssertEqual(PushToTalkManager.legacyState(for: .awaitingResponse), .idle)
    XCTAssertEqual(PushToTalkManager.legacyState(for: .awaitingTools), .idle)
    XCTAssertEqual(PushToTalkManager.legacyState(for: .playing(.nativeRealtime)), .idle)
    XCTAssertEqual(PushToTalkManager.legacyState(for: .terminal(.success)), .idle)
  }

  func testCaptureStartAfterFinalizationProducesStopEffect() {
    let reducer = VoiceTurnReducer()
    let turnID = VoiceTurnID()
    var model = reducer.reduce(.idle, .start(turnID: turnID, intent: .hold)).model
    model = reducer.reduce(model, .finalize(turnID: turnID)).model
    let captureID = VoiceCaptureID(42)

    let result = reducer.reduce(
      model,
      .captureStarted(turnID: turnID, captureID: captureID))

    XCTAssertEqual(result.model.turn?.phase, .finalizing)
    XCTAssertTrue(result.effects.contains(.stopCapture(turnID: turnID, captureID: captureID)))
  }

  func testCancelFromRecordingStopsCaptureAndTerminatesOnce() {
    let reducer = VoiceTurnReducer()
    let turnID = VoiceTurnID()
    let captureID = VoiceCaptureID(9)
    var model = reducer.reduce(.idle, .start(turnID: turnID, intent: .hold)).model
    model = reducer.reduce(model, .captureStarted(turnID: turnID, captureID: captureID)).model

    let cancelled = reducer.reduce(model, .cancel(turnID: turnID, reason: .cancelled))

    XCTAssertEqual(cancelled.model.turn?.phase, .terminal(.cancelled))
    XCTAssertTrue(cancelled.effects.contains(.stopCapture(turnID: turnID, captureID: captureID)))
    XCTAssertEqual(cancelled.effects.filter { effect in
      if case .terminal = effect { return true }
      return false
    }.count, 1)
  }

  @MainActor
  func testHeadlessAutomationRunsRealLifecycleWithoutMicrophonePermission() {
    let manager = PushToTalkManager.shared
    manager.cleanup()
    defer { manager.cleanup() }

    let started = manager.beginPushToTalkForAutomation()
    XCTAssertEqual(started["listening"], "true")
    XCTAssertEqual(VoiceTurnCoordinator.shared.activeTurn?.phase, .recording)

    let stopped = manager.endPushToTalkForAutomation()
    XCTAssertEqual(stopped["finalized"], "true")
    XCTAssertEqual(VoiceTurnCoordinator.shared.model.turn?.phase, .terminal(.tooShort))
    XCTAssertEqual(VoiceTurnCoordinator.shared.model.turn?.projection.hint, "Hold longer to record")
    XCTAssertEqual(VoiceTurnCoordinator.shared.model.staleEventCount, 0)
    XCTAssertEqual(VoiceTurnCoordinator.shared.model.invalidTransitionCount, 0)
  }

  func testLateMicCaptureStartParksWarmInsteadOfLeakingIntoIdlePTT() throws {
    let source = try pushToTalkManagerSource()

    XCTAssertTrue(source.contains("let generation = micCaptureGeneration"))
    XCTAssertTrue(source.contains("self.parkMicCapture(capture, lease: lease, overrideID: overrideDeviceID)"))
    XCTAssertTrue(source.contains("self.audioCaptureService === capture"))
    XCTAssertTrue(source.contains("PushToTalkManager: mic capture start completed after turn ended — parked warm"))
    XCTAssertTrue(source.contains("voiceTurnCoordinator.send(.captureStarted(turnID: turnID, captureID: captureID))"))
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

  func testMicrophonePickerUsesDeviceListenerInsteadOfPolling() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/MainWindow/Pages/Settings/Sections/MicrophonePickerCard.swift")
    // omi-test-quality: source-inspection -- static contract: settings listens for CoreAudio device changes
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertTrue(source.contains("AudioObjectAddPropertyListenerBlock"))
    XCTAssertTrue(source.contains("kAudioHardwarePropertyDevices"))
    XCTAssertTrue(source.contains(".task(id: deviceListObserver.revision)"))
    XCTAssertFalse(source.contains("refreshDevicesPeriodically"))
    XCTAssertFalse(source.contains("Task.sleep"))
  }

  private func pushToTalkManagerSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar/PushToTalkManager.swift")
    // omi-test-quality: source-inspection -- static contract: PTT routes around its parked warm capture
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }
}
