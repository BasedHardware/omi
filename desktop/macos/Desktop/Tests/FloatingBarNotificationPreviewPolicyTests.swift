import XCTest

@testable import Omi_Computer

/// Regression coverage for `FloatingBarNotificationPreviewPolicy` (issue #6765
/// plus the bar-disabled temp-show contract).
///
/// Only the Notifications master toggle (and frequency gate in
/// `NotificationService`) decide whether a notification is owed. The Ask Omi
/// enable toggle controls persistent bar UI only: a disabled bar still presents
/// via temp-show, then re-hides. Muting in-bar previews while the bar stays
/// enabled is the one case that falls back to a native system banner so the
/// notification is never fully silenced.
final class FloatingBarNotificationPreviewPolicyTests: XCTestCase {
  func testPreviewsAndBarEnabledShowsPreviewWithNoForcedBanner() {
    XCTAssertTrue(
      FloatingBarNotificationPreviewPolicy.shouldShowInBarPreview(
        previewsEnabled: true, floatingBarEnabled: true))
    XCTAssertFalse(
      FloatingBarNotificationPreviewPolicy.shouldDeliverSystemBanner(
        previewsEnabled: true, floatingBarEnabled: true, deliverSystemBanner: false))
  }

  func testFloatingBarDisabledPresentsViaTempShowWithNoForcedBanner() {
    XCTAssertTrue(
      FloatingBarNotificationPreviewPolicy.shouldShowInBarPreview(
        previewsEnabled: true, floatingBarEnabled: false),
      "bar disabled + notifications owed must still present the in-bar card via temp-show")
    XCTAssertFalse(
      FloatingBarNotificationPreviewPolicy.shouldDeliverSystemBanner(
        previewsEnabled: true, floatingBarEnabled: false, deliverSystemBanner: false),
      "disabling the bar must not force a contentless system banner")
  }

  func testPreviewsMutedSkipsPreviewAndFallsBackToBanner() {
    XCTAssertFalse(
      FloatingBarNotificationPreviewPolicy.shouldShowInBarPreview(
        previewsEnabled: false, floatingBarEnabled: true))
    XCTAssertTrue(
      FloatingBarNotificationPreviewPolicy.shouldDeliverSystemBanner(
        previewsEnabled: false, floatingBarEnabled: true, deliverSystemBanner: false))
  }

  func testFloatingBarDisabledAndPreviewsMutedStillTempShowsTheCard() {
    XCTAssertTrue(
      FloatingBarNotificationPreviewPolicy.shouldShowInBarPreview(
        previewsEnabled: false, floatingBarEnabled: false),
      "previews muted + bar disabled must still temp-show the card; only the notification toggle silences")
    XCTAssertFalse(
      FloatingBarNotificationPreviewPolicy.shouldDeliverSystemBanner(
        previewsEnabled: false, floatingBarEnabled: false, deliverSystemBanner: false),
      "the combined muted+disabled case uses the card, not a system banner")
  }

  func testBarDisabledDoesNotSilenceWhenMasterNotificationsAreOffTheMasterGateDoes() {
    XCTAssertTrue(
      FloatingBarNotificationPreviewPolicy.shouldShowInBarPreview(
        previewsEnabled: true, floatingBarEnabled: false))
    XCTAssertEqual(
      InsightAssistantTelemetry.Reason.masterNotificationsDisabled.rawValue,
      "master_notifications_disabled",
      "bar disabled + notifications off is suppressed by NotificationService's master toggle, not by preview policy")
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
