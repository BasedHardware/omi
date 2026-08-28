import ScreenCaptureKit
import XCTest

@testable import Omi_Computer

/// The consent-re-prompt defect: with the Screen Recording grant intact, macOS
/// periodically re-confirms consent for app-built content filters, and while that
/// dialog is pending every capture fails with "The user declined TCCs…". Collapsing
/// that error into a generic `.failed` fed the 3 s retry loop that re-armed the dialog
/// (observed three re-prompts in ten minutes). These tests pin the two contracts that
/// fix it: the error is classified, and the classified error is terminal outside the
/// special system modes.
final class ScreenCaptureConsentPolicyTests: XCTestCase {
  // MARK: - Error classification

  func testUserDeclinedSCStreamErrorClassifiesAsPermissionDeclined() {
    let error = NSError(
      domain: SCStreamError.errorDomain,
      code: SCStreamError.userDeclined.rawValue,
      userInfo: nil
    )
    XCTAssertEqual(ScreenCaptureService.classifyCaptureError(error), .permissionDeclined)
  }

  /// The live-machine failure carried the complaint in the message; the substring
  /// fallback must catch it even under an unexpected code, because a missed decline
  /// silently reverts to the retry loop.
  func testDeclinedTCCMessageClassifiesAsPermissionDeclinedRegardlessOfCode() {
    let result = ScreenCaptureService.classifyCaptureError(
      domain: "com.apple.CoreGraphics",
      code: -1,
      description: "The user declined TCCs for application, window, display capture"
    )
    XCTAssertEqual(result, .permissionDeclined)
  }

  func testOtherSCStreamErrorsStayGenericFailures() {
    let error = NSError(
      domain: SCStreamError.errorDomain,
      code: SCStreamError.attemptToStopStreamState.rawValue,
      userInfo: [NSLocalizedDescriptionKey: "The stream is already stopped"]
    )
    XCTAssertEqual(ScreenCaptureService.classifyCaptureError(error), .other)
  }

  func testUnrelatedErrorClassifiesAsOther() {
    let error = NSError(
      domain: NSCocoaErrorDomain, code: 999,
      userInfo: [NSLocalizedDescriptionKey: "connection interrupted"])
    XCTAssertEqual(ScreenCaptureService.classifyCaptureError(error), .other)
  }

  // MARK: - Declined-capture action policy

  /// Exposé / Mission Control produce the same error transiently while they own the
  /// screen; that must stay a wait, never a terminal stop.
  func testSpecialSystemModeWaitsInsteadOfStopping() {
    XCTAssertEqual(
      ScreenCaptureConsentPolicy.actionForDeclinedCapture(
        isInSpecialSystemMode: true, hasNotifiedThisSession: false),
      .waitForSpecialModeToEnd
    )
    XCTAssertEqual(
      ScreenCaptureConsentPolicy.actionForDeclinedCapture(
        isInSpecialSystemMode: true, hasNotifiedThisSession: true),
      .waitForSpecialModeToEnd
    )
  }

  func testDeclineOutsideSpecialModeIsTerminalAndNotifiesOnce() {
    XCTAssertEqual(
      ScreenCaptureConsentPolicy.actionForDeclinedCapture(
        isInSpecialSystemMode: false, hasNotifiedThisSession: false),
      .stopAndNotify(shouldNotify: true)
    )
    XCTAssertEqual(
      ScreenCaptureConsentPolicy.actionForDeclinedCapture(
        isInSpecialSystemMode: false, hasNotifiedThisSession: true),
      .stopAndNotify(shouldNotify: false)
    )
  }

  // MARK: - The retry loops must use the classified capture API
}
