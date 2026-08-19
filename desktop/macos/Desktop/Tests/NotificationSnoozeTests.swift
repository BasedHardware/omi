import XCTest

@testable import Omi_Computer

/// Silencing suggestions for a period is a different statement from hiding the floating
/// bar. `floatingBar_snoozedUntil` documents that hiding the bar must still let
/// notifications through — "an hour of a movie with the bar hidden or off must still
/// nudge". These tests cover the control that does silence them.
final class NotificationSnoozeTests: XCTestCase {
  private let now = Date(timeIntervalSince1970: 1_000_000)

  func testProactiveNotificationIsSuppressedWhileSnoozed() {
    XCTAssertTrue(
      NotificationService.shouldSuppressForSnooze(
        respectFrequency: true,
        snoozedUntil: now.addingTimeInterval(60 * 60),
        now: now))
  }

  func testSnoozeLapsesOnItsOwn() {
    XCTAssertFalse(
      NotificationService.shouldSuppressForSnooze(
        respectFrequency: true,
        snoozedUntil: now.addingTimeInterval(-1),
        now: now),
      "a snooze that has passed must stop suppressing without any explicit clear")
  }

  func testNoSnoozeSetDeliversNormally() {
    XCTAssertFalse(
      NotificationService.shouldSuppressForSnooze(
        respectFrequency: true, snoozedUntil: nil, now: now))
  }

  /// `respectFrequency: false` is the existing proactive/functional split. A user who
  /// silenced suggestions for eight hours must still be told that screen recording broke,
  /// or the prompt that explains how to fix it is exactly what the snooze swallows.
  func testFunctionalNotificationIsNotSuppressedWhileSnoozed() {
    XCTAssertFalse(
      NotificationService.shouldSuppressForSnooze(
        respectFrequency: false,
        snoozedUntil: now.addingTimeInterval(60 * 60),
        now: now))
  }

  func testSnoozeRoundTripsThroughDefaults() throws {
    let defaults = try XCTUnwrap(UserDefaults(suiteName: "omi.tests.snooze"))
    defaults.removePersistentDomain(forName: "omi.tests.snooze")

    XCTAssertNil(NotificationService.currentSnoozeExpiry(defaults: defaults))

    NotificationService.snoozeNotifications(for: 4 * 60 * 60, now: now, defaults: defaults)
    let stored = try XCTUnwrap(NotificationService.currentSnoozeExpiry(defaults: defaults))
    XCTAssertEqual(stored.timeIntervalSince(now), 4 * 60 * 60, accuracy: 1)

    NotificationService.endNotificationSnooze(defaults: defaults)
    XCTAssertNil(
      NotificationService.currentSnoozeExpiry(defaults: defaults),
      "resuming must clear the snooze rather than wait it out")
  }

  /// The snooze key must not collide with the bar's, which carries the opposite meaning.
  func testSnoozeKeyIsDistinctFromFloatingBarSnooze() {
    XCTAssertEqual(
      NotificationService.notificationsSnoozedUntilDefaultsKey, "notifications_snoozedUntil")
    XCTAssertNotEqual(
      NotificationService.notificationsSnoozedUntilDefaultsKey, "floatingBar_snoozedUntil")
  }

  /// Withholding on a snooze defers rather than retires, the same guarantee as presence:
  /// the suggestion is not written to the dedup window, so it survives the silence.
  func testSnoozeSuppressionIsADistinctDeliveryOutcome() {
    XCTAssertEqual(
      SuggestionAssistantTelemetry.DeliveryOutcome.suppressedSnoozed.rawValue,
      "suppressed_snoozed")
    XCTAssertNotEqual(
      SuggestionAssistantTelemetry.DeliveryOutcome.suppressedSnoozed, .filteredDuplicate)
    XCTAssertNotEqual(
      SuggestionAssistantTelemetry.DeliveryOutcome.suppressedSnoozed, .suppressedPresenting)
  }

  func testSnoozeReasonIsRepresentableInDeliveryTelemetry() {
    XCTAssertEqual(InsightAssistantTelemetry.Reason.userSnoozed.rawValue, "user_snoozed")
    XCTAssertTrue(InsightAssistantTelemetry.Reason.allCases.contains(.userSnoozed))
  }

  func testOfferedDurationsAreSaneAndAscending() {
    let seconds = NotificationService.snoozeDurations.map(\.seconds)
    XCTAssertEqual(seconds, seconds.sorted(), "durations should read shortest-first in the menu")
    XCTAssertEqual(seconds.first, 60 * 60)
    XCTAssertTrue(seconds.allSatisfy { $0 > 0 })
  }
}
