import XCTest

@testable import Omi_Computer

/// The menu bar and the notch cluster are two surfaces over one piece of state. These pin
/// the parts of that contract that do not need a live plugin, paywall, or TCC grant.
final class SystemCaptureOutcomeTests: XCTestCase {
  /// A refused enable must leave the control reading OFF. Reflecting the *request* instead
  /// of the *outcome* is how a toggle ends up showing ON while capture is not running.
  func testOnlyEnabledReadsAsOn() {
    XCTAssertTrue(SystemCaptureOutcome.enabled.resultingIsOn)
    XCTAssertFalse(SystemCaptureOutcome.disabled.resultingIsOn)
    XCTAssertFalse(SystemCaptureOutcome.blockedPaywall.resultingIsOn)
    XCTAssertFalse(SystemCaptureOutcome.blockedPermission.resultingIsOn)
    XCTAssertFalse(SystemCaptureOutcome.failedToStart.resultingIsOn)
  }

  func testRefusalsAreDistinguishableFromAPlainDisable() {
    // The caller needs to tell "user turned it off" apart from "we refused", because only
    // the latter has already surfaced an upgrade prompt or a permission pane.
    XCTAssertNotEqual(SystemCaptureOutcome.blockedPaywall, .disabled)
    XCTAssertNotEqual(SystemCaptureOutcome.blockedPermission, .disabled)
    XCTAssertNotEqual(SystemCaptureOutcome.failedToStart, .disabled)
    XCTAssertNotEqual(SystemCaptureOutcome.blockedPaywall, .blockedPermission)
  }

  func testMicrophonePromptOnlyBelongsToAnOffToEnabledTransition() {
    XCTAssertTrue(
      AudioRecordingPermissionTransitionPolicy.shouldRequestPermission(
        currentMode: .off,
        requestedMode: .onlyMeetings,
        permissionGranted: false))
    XCTAssertFalse(
      AudioRecordingPermissionTransitionPolicy.shouldRequestPermission(
        currentMode: .onlyMeetings,
        requestedMode: .always,
        permissionGranted: false),
      "Changing enabled modes must not reopen a denied permission flow")
    XCTAssertFalse(
      AudioRecordingPermissionTransitionPolicy.shouldRequestPermission(
        currentMode: .off,
        requestedMode: .always,
        permissionGranted: true))
    XCTAssertFalse(
      AudioRecordingPermissionTransitionPolicy.shouldRequestPermission(
        currentMode: .always,
        requestedMode: .off,
        permissionGranted: false))
  }
}
