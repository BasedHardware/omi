import XCTest

@testable import Omi_Computer

/// Regression coverage for `FloatingBarNotificationPreviewPolicy` (issue #6765).
///
/// Proactive notifications default to `deliverSystemBanner: false`, so the
/// Floating Bar in-app preview is their only delivery path today. Muting that
/// preview without a fallback would silence those notifications entirely.
/// These tests pin the policy that keeps a notification delivered via the
/// native system banner only when the user *explicitly* muted in-bar previews
/// while the Floating Bar stayed enabled. Merely disabling the Floating Bar
/// must not force a banner: `NotificationService.sendNotification` documents
/// that a contentless system banner (no conversation context) was previously
/// reported as confusing, which is why floating-bar-only notifications stay
/// silent when the bar itself is off — same as before this policy existed.
final class FloatingBarNotificationPreviewPolicyTests: XCTestCase {
  func testPreviewsAndBarEnabledShowsPreviewWithNoForcedBanner() {
    XCTAssertTrue(
      FloatingBarNotificationPreviewPolicy.shouldShowInBarPreview(
        previewsEnabled: true, floatingBarEnabled: true))
    XCTAssertFalse(
      FloatingBarNotificationPreviewPolicy.shouldDeliverSystemBanner(
        previewsEnabled: true, floatingBarEnabled: true, deliverSystemBanner: false))
  }

  func testFloatingBarDisabledSkipsPreviewWithNoForcedBanner() {
    XCTAssertFalse(
      FloatingBarNotificationPreviewPolicy.shouldShowInBarPreview(
        previewsEnabled: true, floatingBarEnabled: false))
    XCTAssertFalse(
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

  func testFloatingBarDisabledStillNoForcedBannerEvenWithPreviewsMuted() {
    XCTAssertFalse(
      FloatingBarNotificationPreviewPolicy.shouldShowInBarPreview(
        previewsEnabled: false, floatingBarEnabled: false))
    XCTAssertFalse(
      FloatingBarNotificationPreviewPolicy.shouldDeliverSystemBanner(
        previewsEnabled: false, floatingBarEnabled: false, deliverSystemBanner: false))
  }

  func testExplicitSystemBannerAlwaysDeliversRegardlessOfPreviewState() {
    XCTAssertTrue(
      FloatingBarNotificationPreviewPolicy.shouldDeliverSystemBanner(
        previewsEnabled: true, floatingBarEnabled: true, deliverSystemBanner: true))
    XCTAssertTrue(
      FloatingBarNotificationPreviewPolicy.shouldDeliverSystemBanner(
        previewsEnabled: false, floatingBarEnabled: false, deliverSystemBanner: true))
  }

  func testExplicitBannerDoesNotDuplicateAnAcceptedFloatingBarPresentation() {
    XCTAssertFalse(
      FloatingBarNotificationPreviewPolicy.shouldDeliverSystemBannerAfterFloatingBar(
        previewsEnabled: true,
        floatingBarEnabled: true,
        deliverSystemBanner: true,
        floatingBarAccepted: true))
    XCTAssertTrue(
      FloatingBarNotificationPreviewPolicy.shouldDeliverSystemBannerAfterFloatingBar(
        previewsEnabled: true,
        floatingBarEnabled: true,
        deliverSystemBanner: true,
        floatingBarAccepted: false))
  }

  func testDirectorMutedPreviewFallsBackToBannerInsteadOfSilentQuotaBurn() {
    // Context-director presentation must use this policy: muted previews with
    // the floating bar still enabled keep a visible system-banner surface.
    XCTAssertFalse(
      FloatingBarNotificationPreviewPolicy.shouldShowInBarPreview(
        previewsEnabled: false, floatingBarEnabled: true))
    XCTAssertTrue(
      FloatingBarNotificationPreviewPolicy.shouldDeliverSystemBanner(
        previewsEnabled: false, floatingBarEnabled: true, deliverSystemBanner: false),
      "muted in-bar preview must keep a banner surface so director delivery is visible")
  }

  @MainActor
  func testDirectorOwnerRefusalInvokesDroppedCallbackExactlyOnce() {
    var droppedCount = 0
    let service = NotificationService(registerWithSystemNotificationCenter: false)
    let result = service.presentContextDirectorNotification(
      ownerID: "",
      title: "Suggestion",
      message: "Do the next thing",
      decisionType: "suggestion",
      context: FloatingBarNotificationContext(
        sourceTitle: "Context director",
        assistantId: "context-director"),
      onDropped: { droppedCount += 1 })

    XCTAssertEqual(result, .rejectedOwnerChange)
    XCTAssertEqual(droppedCount, 1)
  }
}
