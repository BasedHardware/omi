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
}
