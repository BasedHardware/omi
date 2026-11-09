import XCTest

@testable import Omi_Computer

final class SleepCaptureRearmPolicyTests: XCTestCase {
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
