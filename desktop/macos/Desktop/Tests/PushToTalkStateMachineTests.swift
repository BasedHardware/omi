import XCTest

@testable import Omi_Computer

final class PushToTalkStateMachineTests: XCTestCase {
  func testRecordingProjectionComesDirectlyFromAuthoritativePhase() {
    XCTAssertTrue(VoiceTurnPhase.recording.isRecording)
    XCTAssertTrue(VoiceTurnPhase.pendingLockDecision.isRecording)
    XCTAssertTrue(VoiceTurnPhase.lockedRecording.isRecording)
    XCTAssertFalse(VoiceTurnPhase.finalizing.isRecording)
    XCTAssertTrue(VoiceTurnPhase.terminal(.success).isTerminal)
  }

  func testCaptureStartAfterFinalizationProducesStopEffect() {
    let reducer = VoiceTurnReducer()
    let turnID = VoiceTurnID()
    var model = reducer.reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
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
    var model = reducer.reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
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
    let previousAuthOwner = UserDefaults.standard.object(forKey: .authUserId)
    let previousAutomationOwner = UserDefaults.standard.object(forKey: .automationOwnerOverride)
    manager.cleanup()
    UserDefaults.standard.set("ptt-headless-owner", forKey: .authUserId)
    UserDefaults.standard.removeObject(forKey: .automationOwnerOverride)
    defer {
      manager.cleanup()
      if let previousAuthOwner {
        UserDefaults.standard.set(previousAuthOwner, forKey: .authUserId)
      } else {
        UserDefaults.standard.removeObject(forKey: .authUserId)
      }
      if let previousAutomationOwner {
        UserDefaults.standard.set(previousAutomationOwner, forKey: .automationOwnerOverride)
      } else {
        UserDefaults.standard.removeObject(forKey: .automationOwnerOverride)
      }
    }

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
