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

  /// "Until tomorrow" is a wall-clock boundary, not an offset, so the interesting cases are
  /// the ones either side of the resume hour.
  func testUntilTomorrowResumesAtTheNextWorkdayStart() {
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = try! XCTUnwrap(TimeZone(identifier: "Asia/Kolkata"))

    func at(_ hour: Int, _ minute: Int = 0) -> Date {
      calendar.date(from: DateComponents(year: 2026, month: 8, day: 19, hour: hour, minute: minute))!
    }

    // Late evening: resumes 9am the following calendar day, not in an hour at midnight.
    let fromEvening = NotificationService.snoozeUntilTomorrowExpiry(
      now: at(23, 30), calendar: calendar)
    XCTAssertEqual(calendar.component(.hour, from: fromEvening), 9)
    XCTAssertEqual(calendar.component(.day, from: fromEvening), 20)

    // Small hours: already "tomorrow" by the clock, so it resumes this morning rather
    // than waiting 31 hours.
    let fromSmallHours = NotificationService.snoozeUntilTomorrowExpiry(
      now: at(2, 15), calendar: calendar)
    XCTAssertEqual(calendar.component(.hour, from: fromSmallHours), 9)
    XCTAssertEqual(
      calendar.component(.day, from: fromSmallHours), 19,
      "silencing at 2am should resume the same morning, not the next one")

    // Exactly at the boundary counts as passed, so it moves to the next day.
    let fromNine = NotificationService.snoozeUntilTomorrowExpiry(now: at(9, 0), calendar: calendar)
    XCTAssertEqual(calendar.component(.day, from: fromNine), 20)
  }

  func testUntilTomorrowAlwaysProducesAFutureExpiry() {
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = try! XCTUnwrap(TimeZone(identifier: "Asia/Kolkata"))
    for hour in 0...23 {
      let now = calendar.date(
        from: DateComponents(year: 2026, month: 8, day: 19, hour: hour, minute: 30))!
      let expiry = NotificationService.snoozeUntilTomorrowExpiry(now: now, calendar: calendar)
      XCTAssertGreaterThan(expiry, now, "a snooze that expires in the past silences nothing (hour \(hour))")
    }
  }

  func testOfferedDurationsAreSaneAndAscending() {
    let seconds = NotificationService.snoozeDurations.map(\.seconds)
    XCTAssertEqual(seconds, seconds.sorted(), "durations should read shortest-first in the menu")
    XCTAssertEqual(seconds.first, 60 * 60)
    XCTAssertTrue(seconds.allSatisfy { $0 > 0 })
  }
}
