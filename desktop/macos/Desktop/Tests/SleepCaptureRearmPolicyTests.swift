import XCTest

@testable import Omi_Computer

final class SleepCaptureRearmPolicyTests: XCTestCase {
  @MainActor
  private func makeSleepingState() -> AppState {
    let previousMode = AssistantSettings.shared.audioRecordingMode
    AssistantSettings.shared.audioRecordingMode = .always
    let state = AppState()
    state.servicesCoordinator.removeLifecycleObservers()
    state.notificationHealthTimer?.invalidate()
    state.wasTranscribingBeforeSleep = true
    addTeardownBlock { @MainActor in
      state.cancelDarkWakeCaptureRearm()
      AssistantSettings.shared.audioRecordingMode = previousMode
    }
    return state
  }

  @MainActor
  func testFailedDarkWakeStartLeavesFullWakeAbleToRetry() {
    let state = makeSleepingState()

    XCTAssertTrue(state.claimSleepRestart(signal: .stillScheduled))
    // A refused startup leaves the production capture state stopped.
    XCTAssertFalse(state.isTranscribing)
    XCTAssertTrue(state.wasTranscribingBeforeSleep)
    XCTAssertTrue(state.claimSleepRestart(signal: .didWake))
    XCTAssertFalse(state.wasTranscribingBeforeSleep)
    XCTAssertFalse(state.claimSleepRestart(signal: .didWake))
  }

  @MainActor
  func testSuccessfulDarkWakeStartDoesNotDuplicateCaptureAtFullWake() {
    let state = makeSleepingState()

    XCTAssertTrue(state.claimSleepRestart(signal: .stillScheduled))
    state.isTranscribing = true

    XCTAssertFalse(state.claimSleepRestart(signal: .didWake))
    XCTAssertFalse(state.wasTranscribingBeforeSleep)
    XCTAssertFalse(state.claimSleepRestart(signal: .stillScheduled))
  }

  @MainActor
  func testFullWakeCancelsThePendingProbeAndRetainsItsRestart() async {
    let state = makeSleepingState()
    state.armDarkWakeCaptureRearm()
    let pendingProbe = state.darkWakeRearmTask
    XCTAssertNotNil(pendingProbe)

    state.cancelDarkWakeCaptureRearm()
    await pendingProbe?.value

    XCTAssertNil(state.darkWakeRearmTask)
    XCTAssertFalse(state.isTranscribing)
    XCTAssertTrue(state.claimSleepRestart(signal: .didWake))
    XCTAssertFalse(state.wasTranscribingBeforeSleep)
  }

  func testDarkWakeRestartsAlwaysOnCaptureThatSleepStopped() {
    let action = SleepCaptureRearmPolicy.action(
      wasTranscribingBeforeSleep: true,
      recordingMode: .always,
      isTranscribing: false,
      signal: .stillScheduled
    )

    XCTAssertEqual(action, .restart)
  }

  func testDarkWakeLeavesMeetingOnlyCaptureForTheRealWake() {
    let action = SleepCaptureRearmPolicy.action(
      wasTranscribingBeforeSleep: true,
      recordingMode: .onlyMeetings,
      isTranscribing: false,
      signal: .stillScheduled
    )

    XCTAssertEqual(action, .leaveStopped)
  }

  func testDarkWakeDoesNotStartWhenRecordingIsOff() {
    let action = SleepCaptureRearmPolicy.action(
      wasTranscribingBeforeSleep: true,
      recordingMode: .off,
      isTranscribing: false,
      signal: .stillScheduled
    )

    XCTAssertEqual(action, .leaveStopped)
  }

  func testDarkWakeDoesNotRestartASessionThatIsAlreadyRunning() {
    let action = SleepCaptureRearmPolicy.action(
      wasTranscribingBeforeSleep: true,
      recordingMode: .always,
      isTranscribing: true,
      signal: .stillScheduled
    )

    XCTAssertEqual(action, .leaveStopped)
  }

  func testDarkWakeDoesNothingWhenCaptureWasAlreadyStopped() {
    let action = SleepCaptureRearmPolicy.action(
      wasTranscribingBeforeSleep: false,
      recordingMode: .always,
      isTranscribing: false,
      signal: .stillScheduled
    )

    XCTAssertEqual(action, .leaveStopped)
  }

  func testRealWakeStillRestartsMeetingCapture() {
    let action = SleepCaptureRearmPolicy.action(
      wasTranscribingBeforeSleep: true,
      recordingMode: .onlyMeetings,
      isTranscribing: false,
      signal: .didWake
    )

    XCTAssertEqual(action, .restart)
  }

  func testRealWakeDoesNotRestartWhenRecordingIsOff() {
    let action = SleepCaptureRearmPolicy.action(
      wasTranscribingBeforeSleep: true,
      recordingMode: .off,
      isTranscribing: false,
      signal: .didWake
    )

    XCTAssertEqual(action, .leaveStopped)
  }
}
