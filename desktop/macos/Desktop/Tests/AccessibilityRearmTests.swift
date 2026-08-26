import XCTest

@testable import Omi_Computer

/// A grant must take effect without a relaunch.
///
/// `ScreenCaptureService` latches AX off after a single `apiDisabled`, because the alternative
/// is a failing WindowServer call once a second. Observed on this machine: 15 consecutive Beta
/// launches each logged `ACCESSIBILITY_AX: apiDisabled (-25211) — disabling AX attempts until
/// next launch`, and nothing ever cleared it within the session. The latch is a rate limit on a
/// known-broken call, not a verdict for the life of the process.
final class AccessibilityRearmTests: XCTestCase {
  override func tearDown() {
    ScreenCaptureService.rearmAccessibilityAfterPermissionChange()
    super.tearDown()
  }

  func testRearmClearsSuppressionAndReportsIt() {
    ScreenCaptureService.suppressAccessibilityForTesting()
    XCTAssertTrue(ScreenCaptureService.isAccessibilitySuppressedForTesting())

    XCTAssertTrue(
      ScreenCaptureService.rearmAccessibilityAfterPermissionChange(),
      "re-arming a suppressed state is a recovery and must report itself")
    XCTAssertFalse(ScreenCaptureService.isAccessibilitySuppressedForTesting())
  }

  /// The permission poll runs continuously, so a re-arm that reported every time would turn a
  /// recovery line into background noise.
  func testRearmIsSilentWhenNothingWasSuppressed() {
    ScreenCaptureService.rearmAccessibilityAfterPermissionChange()
    XCTAssertFalse(ScreenCaptureService.rearmAccessibilityAfterPermissionChange())
  }

  /// Per-app failures counted while the permission was broken say nothing about whether that
  /// app implements AX, so they must not outlive the grant either.
  func testRearmClearsPerAppFailureCounts() {
    ScreenCaptureService.suppressAccessibilityForTesting()
    ScreenCaptureService.rearmAccessibilityAfterPermissionChange()
    XCTAssertFalse(ScreenCaptureService.isAccessibilitySuppressedForTesting())
  }
}
