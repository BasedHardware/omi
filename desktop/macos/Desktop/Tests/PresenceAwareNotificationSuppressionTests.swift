import XCTest

@testable import Omi_Computer

/// A proactive notification is addressed to one person. Sharing a screen broadcasts every
/// surface Omi draws to the whole call, so a private nudge reaches an audience it was never
/// written for — and once seen, that cannot be taken back.
///
/// Being on a call is a different matter. Nobody can see the screen, and the moment is often
/// exactly when the nudge is worth most: mid-call with someone is when "you owe them a task"
/// is useful. This originally suppressed on either signal, treating the interruption as the
/// harm. It is not. What must not happen on a call is the nudge being *spoken*.
final class PresenceAwareNotificationSuppressionTests: XCTestCase {
  private func presence(shared: Bool, onCall: Bool) -> NotificationService.PresenceSignals {
    NotificationService.PresenceSignals(screenShared: shared, onCall: onCall)
  }

  func testProactiveNotificationIsSuppressedWhileSharing() {
    XCTAssertTrue(
      NotificationService.shouldSuppressForPresence(
        respectFrequency: true, presence: presence(shared: true, onCall: false)))
  }

  /// The case this change exists for: on a call, not sharing, the nudge goes through.
  func testProactiveNotificationIsDeliveredOnACallWithoutSharing() {
    XCTAssertFalse(
      NotificationService.shouldSuppressForPresence(
        respectFrequency: true, presence: presence(shared: false, onCall: true)))
  }

  func testProactiveNotificationIsDeliveredWhenAlone() {
    XCTAssertFalse(
      NotificationService.shouldSuppressForPresence(
        respectFrequency: true, presence: presence(shared: false, onCall: false)))
  }

  /// Sharing during a call still suppresses — the visibility harm does not care why the
  /// screen is up.
  func testSharingDuringACallStillSuppresses() {
    XCTAssertTrue(
      NotificationService.shouldSuppressForPresence(
        respectFrequency: true, presence: presence(shared: true, onCall: true)))
  }

  /// `respectFrequency: false` is the existing proactive/functional split. Functional
  /// notices — the screen-recording repair prompt, Crisp support replies, the onboarding
  /// test — must still reach the user mid-share. Suppressing the capture-repair prompt
  /// during a share is precisely how a broken capture would stay broken, since that prompt
  /// is what tells the user to fix it.
  func testFunctionalNotificationIsNotSuppressedWhileSharing() {
    XCTAssertFalse(
      NotificationService.shouldSuppressForPresence(
        respectFrequency: false, presence: presence(shared: true, onCall: false)))
  }

  func testFunctionalNotificationIsNotSuppressedWhenAlone() {
    XCTAssertFalse(
      NotificationService.shouldSuppressForPresence(
        respectFrequency: false, presence: presence(shared: false, onCall: false)))
  }

  // MARK: - Speech has no private surface

  /// A banner on a call is seen by the user alone; the same text read aloud is heard by
  /// everyone in the room and everyone on the call, with no screen share needed.
  func testDeliveredNotificationStaysSilentOnACall() {
    XCTAssertTrue(
      NotificationService.shouldWithholdSpeechForPresence(
        presence: presence(shared: false, onCall: true)))
  }

  func testDeliveredNotificationStaysSilentWhileSharing() {
    XCTAssertTrue(
      NotificationService.shouldWithholdSpeechForPresence(
        presence: presence(shared: true, onCall: false)))
  }

  func testDeliveredNotificationSpeaksWhenAlone() {
    XCTAssertFalse(
      NotificationService.shouldWithholdSpeechForPresence(
        presence: presence(shared: false, onCall: false)))
  }

  /// The visual delivery and the voice are decided separately: on a call the nudge is shown
  /// and not spoken, which is the whole shape of this change.
  func testOnACallTheNudgeIsShownButNotSpoken() {
    let onCall = presence(shared: false, onCall: true)
    XCTAssertFalse(
      NotificationService.shouldSuppressForPresence(respectFrequency: true, presence: onCall))
    XCTAssertNil(
      NotificationSpeech.utterance(
        message: "You said you'd send Maya the spec.",
        isEnabled: true,
        isProactive: true,
        othersCanHear: NotificationService.shouldWithholdSpeechForPresence(presence: onCall)))
  }

  func testAloneTheSameNudgeIsSpoken() {
    let alone = presence(shared: false, onCall: false)
    XCTAssertEqual(
      NotificationSpeech.utterance(
        message: "You said you'd send Maya the spec.",
        isEnabled: true,
        isProactive: true,
        othersCanHear: NotificationService.shouldWithholdSpeechForPresence(presence: alone)),
      "You said you'd send Maya the spec.")
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
