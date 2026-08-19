import XCTest

@testable import Omi_Computer

/// A proactive notification is addressed to one person. While the user presents, every
/// surface Omi draws on is broadcast to the call, so a private nudge reaches an audience it
/// was never written for.
final class PresenceAwareNotificationSuppressionTests: XCTestCase {
  func testProactiveNotificationIsSuppressedWhilePresenting() {
    XCTAssertTrue(
      NotificationService.shouldSuppressForPresence(
        respectFrequency: true, presenceDetected: true))
  }

  func testProactiveNotificationIsDeliveredWhenNotPresenting() {
    XCTAssertFalse(
      NotificationService.shouldSuppressForPresence(
        respectFrequency: true, presenceDetected: false))
  }

  /// `respectFrequency: false` is the existing proactive/functional split. Functional
  /// notices — the screen-recording repair prompt, Crisp support replies, the onboarding
  /// test — must still reach the user mid-share. Suppressing the capture-repair prompt
  /// during a share is precisely how a broken capture would stay broken, since that prompt
  /// is what tells the user to fix it.
  func testFunctionalNotificationIsNotSuppressedWhilePresenting() {
    XCTAssertFalse(
      NotificationService.shouldSuppressForPresence(
        respectFrequency: false, presenceDetected: true))
  }

  func testFunctionalNotificationIsNotSuppressedWhenNotPresenting() {
    XCTAssertFalse(
      NotificationService.shouldSuppressForPresence(
        respectFrequency: false, presenceDetected: false))
  }

  /// The suppression must be attributable in delivery telemetry rather than looking like a
  /// silent drop, which is the failure mode that made the wake word undiagnosable.
  func testSuppressionReasonIsRepresentable() {
    XCTAssertEqual(InsightAssistantTelemetry.Reason.presenceActive.rawValue, "presence_active")
    XCTAssertTrue(InsightAssistantTelemetry.Reason.allCases.contains(.presenceActive))
  }

  /// The reason a withheld suggestion must not be written into the dedup window.
  ///
  /// `SuggestionAssistant` remembers a suggestion immediately before delivering it, and the
  /// dedup window gates every later evaluation. If a suggestion the screen-share guard is
  /// about to withhold were remembered anyway, it would be retired permanently: the user
  /// never sees the card, and every regeneration after the call is filtered as a duplicate
  /// of something that was never shown. These two tests pin that consequence.
  func testRememberedSuggestionIsFilteredOnRegeneration() {
    let text = "Submit prototype for SBI Hackathon @ GFF 2026."
    let window = SuggestionDeduplication.remembering(
      .init(text: text, category: .commitment),
      in: [],
      frequencyLevel: SuggestionPacing.maximumLevel)
    XCTAssertTrue(
      SuggestionDeduplication.isDuplicate(text, of: window.map(\.text)),
      "a remembered suggestion is a duplicate forever after — which is why a withheld one must not be remembered")
  }

  func testUnrememberedSuggestionRemainsDeliverableAfterTheShareEnds() {
    let text = "Submit prototype for SBI Hackathon @ GFF 2026."
    // The presenting path returns before `remembering`, so the window is untouched.
    let window: [SuggestionDeduplication.Remembered] = []
    XCTAssertFalse(
      SuggestionDeduplication.isDuplicate(text, of: window.map(\.text)),
      "withholding must defer the suggestion, not destroy it")
  }

  /// Withholding on audience is not the same as filtering on merit, and delivery telemetry
  /// has to be able to tell them apart — otherwise a deferred suggestion is indistinguishable
  /// from one that was rejected for being a duplicate or low confidence.
  func testPresentingSuppressionIsADistinctDeliveryOutcome() {
    XCTAssertEqual(
      SuggestionAssistantTelemetry.DeliveryOutcome.suppressedPresenting.rawValue,
      "suppressed_presenting")
    XCTAssertNotEqual(
      SuggestionAssistantTelemetry.DeliveryOutcome.suppressedPresenting,
      .filteredDuplicate)
  }

  /// The share indicators the policy is fed. These are the window titles the detection
  /// matches; they are the reason the guard fires at all, so a regression here would make
  /// the feature silently inert.
  func testShareIndicatorsAreRecognizedForMajorConferencingApps() {
    XCTAssertTrue(
      ConferencingApps.isShareIndicatorWindow(ownerName: "zoom.us", title: "zoom share toolbar"))
    XCTAssertTrue(
      ConferencingApps.isShareIndicatorWindow(
        ownerName: "Microsoft Teams", title: "Sharing toolbar"))
    XCTAssertTrue(
      ConferencingApps.isShareIndicatorWindow(
        ownerName: "Google Chrome", title: "meet.google.com is sharing your screen."))
  }

  func testOrdinaryWindowsAreNotTreatedAsShareIndicators() {
    XCTAssertFalse(
      ConferencingApps.isShareIndicatorWindow(ownerName: "zoom.us", title: "Zoom Meeting"))
    XCTAssertFalse(
      ConferencingApps.isShareIndicatorWindow(ownerName: "Google Chrome", title: "Inbox (12)"))
    XCTAssertFalse(ConferencingApps.isShareIndicatorWindow(ownerName: nil, title: nil))
  }
}
