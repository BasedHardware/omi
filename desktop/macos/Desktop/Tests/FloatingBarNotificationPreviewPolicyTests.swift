import XCTest

@testable import Omi_Computer

/// Regression coverage for `FloatingBarNotificationPreviewPolicy` (issue #6765).
///
/// Proactive notifications default to `deliverSystemBanner: false`, so the
/// Floating Bar in-app preview is their only delivery path today. Muting that
/// preview without a fallback would silence those notifications entirely.
/// These tests pin the policy that keeps a notification delivered via the
/// native system banner whenever the in-bar preview is suppressed.
final class FloatingBarNotificationPreviewPolicyTests: XCTestCase {
  func testPreviewsAndBarEnabledShowsPreviewWithNoForcedBanner() {
    XCTAssertTrue(
      FloatingBarNotificationPreviewPolicy.shouldShowInBarPreview(
        previewsEnabled: true, floatingBarEnabled: true))
    XCTAssertFalse(
      FloatingBarNotificationPreviewPolicy.shouldDeliverSystemBanner(
        previewsEnabled: true, floatingBarEnabled: true, deliverSystemBanner: false))
  }

  func testFloatingBarDisabledSkipsPreviewAndFallsBackToBanner() {
    XCTAssertFalse(
      FloatingBarNotificationPreviewPolicy.shouldShowInBarPreview(
        previewsEnabled: true, floatingBarEnabled: false))
    XCTAssertTrue(
      FloatingBarNotificationPreviewPolicy.shouldDeliverSystemBanner(
        previewsEnabled: true, floatingBarEnabled: false, deliverSystemBanner: false))
  }

  func testPreviewsMutedSkipsPreviewAndFallsBackToBanner() {
    XCTAssertFalse(
      FloatingBarNotificationPreviewPolicy.shouldShowInBarPreview(
        previewsEnabled: false, floatingBarEnabled: true))
    XCTAssertTrue(
      FloatingBarNotificationPreviewPolicy.shouldDeliverSystemBanner(
        previewsEnabled: false, floatingBarEnabled: true, deliverSystemBanner: false))
  }

  func testExplicitSystemBannerAlwaysDeliversRegardlessOfPreviewState() {
    XCTAssertTrue(
      FloatingBarNotificationPreviewPolicy.shouldDeliverSystemBanner(
        previewsEnabled: true, floatingBarEnabled: true, deliverSystemBanner: true))
    XCTAssertTrue(
      FloatingBarNotificationPreviewPolicy.shouldDeliverSystemBanner(
        previewsEnabled: false, floatingBarEnabled: false, deliverSystemBanner: true))
  }
}
