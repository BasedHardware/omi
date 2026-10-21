import Foundation
import XCTest

@testable import Omi_Computer

final class TaskRecurrenceDatePolicyTests: XCTestCase {
  func testEverySupportedRuleAdvancesOneOccurrenceEvenWhenCompletedEarly() throws {
    let calendar = try makeCalendar()
    let due = try date(2026, 10, 9, calendar: calendar)
    let now = try date(2026, 10, 8, calendar: calendar)
    let cases = [
      ("daily", 2026, 10, 10),
      ("weekdays", 2026, 10, 12),
      ("weekly", 2026, 10, 16),
      ("biweekly", 2026, 10, 23),
      ("monthly", 2026, 11, 9),
    ]
    for (rule, year, month, day) in cases {
      XCTAssertEqual(
        TaskRecurrenceDatePolicy.nextDueDate(from: due, rule: rule, now: now, calendar: calendar),
        try date(year, month, day, calendar: calendar), rule)
    }
  }

  func testEverySupportedRuleAcceptsAnOccurrenceExactlyEqualToCapturedNow() throws {
    let calendar = try makeCalendar()
    let due = try date(2026, 10, 9, calendar: calendar)
    for rule in ["daily", "weekdays", "weekly", "biweekly", "monthly"] {
      let first = try XCTUnwrap(
        TaskRecurrenceDatePolicy.nextDueDate(from: due, rule: rule, now: due, calendar: calendar))
      XCTAssertEqual(
        TaskRecurrenceDatePolicy.nextDueDate(from: due, rule: rule, now: first, calendar: calendar), first, rule)
      XCTAssertGreaterThan(first, due)
    }
  }

  func testLateCompletionSkipsMissedOccurrencesWithoutChangingTheRulePhase() throws {
    let calendar = try makeCalendar()
    let due = try date(2026, 10, 1, calendar: calendar)
    let now = try date(2026, 10, 20, hour: 10, calendar: calendar)
    for (rule, month, day) in [
      ("daily", 10, 21), ("weekdays", 10, 21), ("weekly", 10, 22),
      ("biweekly", 10, 29), ("monthly", 11, 1),
    ] {
      let result = TaskRecurrenceDatePolicy.nextDueDate(from: due, rule: rule, now: now, calendar: calendar)
      XCTAssertEqual(result, try date(2026, month, day, calendar: calendar), rule)
      XCTAssertGreaterThanOrEqual(try XCTUnwrap(result), now)
    }
  }

  func testWeekdaysSkipTheSuppliedCalendarsWeekendWhenCatchingUp() throws {
    let calendar = try makeCalendar()
    let due = try date(2026, 10, 8, calendar: calendar)
    let now = try date(2026, 10, 10, hour: 10, calendar: calendar)
    let result = TaskRecurrenceDatePolicy.nextDueDate(from: due, rule: "weekdays", now: now, calendar: calendar)
    XCTAssertEqual(result, try date(2026, 10, 12, calendar: calendar))
    XCTAssertFalse(calendar.isDateInWeekend(try XCTUnwrap(result)))
  }

  func testMonthlyCatchUpPreservesSequentialNonLeapMonthEndClamping() throws {
    let calendar = try makeCalendar()
    let due = try date(2026, 1, 31, calendar: calendar)
    let now = try date(2026, 3, 1, calendar: calendar)
    let result = TaskRecurrenceDatePolicy.nextDueDate(from: due, rule: "monthly", now: now, calendar: calendar)
    XCTAssertEqual(result, try date(2026, 3, 28, calendar: calendar))
    XCTAssertNotEqual(result, calendar.date(byAdding: .month, value: 2, to: due))
  }

  func testMonthlyCatchUpPreservesSequentialLeapMonthEndClamping() throws {
    let calendar = try makeCalendar()
    let due = try date(2024, 1, 31, calendar: calendar)
    let february = try date(2024, 2, 29, calendar: calendar)
    XCTAssertEqual(
      TaskRecurrenceDatePolicy.nextDueDate(from: due, rule: "monthly", now: february, calendar: calendar), february)
    XCTAssertEqual(
      TaskRecurrenceDatePolicy.nextDueDate(
        from: due, rule: "monthly", now: try date(2024, 3, 1, calendar: calendar), calendar: calendar),
      try date(2024, 3, 29, calendar: calendar))
  }

  func testMonthlyShortMonthDoesNotRestoreTheOriginalMonthEndAfterItClamps() throws {
    let calendar = try makeCalendar()
    for startingDay in [29, 30, 31] {
      XCTAssertEqual(
        TaskRecurrenceDatePolicy.nextDueDate(
          from: try date(2026, 1, startingDay, calendar: calendar), rule: "monthly",
          now: try date(2026, 4, 1, calendar: calendar), calendar: calendar),
        try date(2026, 4, 28, calendar: calendar))
    }
  }

  func testDailySpringTransitionPreservesWallTimeRatherThanAdding24Hours() throws {
    let calendar = try makeCalendar(timeZone: "America/New_York")
    let due = try date(2026, 3, 7, calendar: calendar)
    let next = try XCTUnwrap(
      TaskRecurrenceDatePolicy.nextDueDate(from: due, rule: "daily", now: due, calendar: calendar))
    XCTAssertEqual(next, try date(2026, 3, 8, calendar: calendar))
    XCTAssertEqual(next.timeIntervalSince(due), 23 * 60 * 60)
  }

  func testDailyFallTransitionPreservesWallTimeRatherThanAdding24Hours() throws {
    let calendar = try makeCalendar(timeZone: "America/New_York")
    let due = try date(2026, 10, 31, calendar: calendar)
    let next = try XCTUnwrap(
      TaskRecurrenceDatePolicy.nextDueDate(from: due, rule: "daily", now: due, calendar: calendar))
    XCTAssertEqual(next, try date(2026, 11, 1, calendar: calendar))
    XCTAssertEqual(next.timeIntervalSince(due), 25 * 60 * 60)
  }

  func testSpringGapCatchUpRetainsFoundationsSequentialAdjustment() throws {
    let calendar = try makeCalendar(timeZone: "America/New_York")
    let due = try date(2026, 3, 7, hour: 2, minute: 30, calendar: calendar)
    // These are the existing Calendar additions, not a new gap-time policy.
    let adjusted = try XCTUnwrap(calendar.date(byAdding: .day, value: 1, to: due))
    let following = try XCTUnwrap(calendar.date(byAdding: .day, value: 1, to: adjusted))
    let expected = try XCTUnwrap(calendar.date(byAdding: .day, value: 1, to: following))
    let result = try XCTUnwrap(
      TaskRecurrenceDatePolicy.nextDueDate(
        from: due, rule: "daily", now: following.addingTimeInterval(1), calendar: calendar))
    XCTAssertEqual(result, expected)
    XCTAssertEqual(calendar.component(.hour, from: result), calendar.component(.hour, from: following))
    XCTAssertEqual(calendar.component(.minute, from: result), 30)
  }

  func testFallRepeatedHourRetainsFoundationsOneCalendarDayAdvancement() throws {
    let calendar = try makeCalendar(timeZone: "America/New_York")
    let due = try date(2026, 10, 31, hour: 1, minute: 30, calendar: calendar)
    let repeatedDay = try XCTUnwrap(calendar.date(byAdding: .day, value: 1, to: due))
    let following = try XCTUnwrap(calendar.date(byAdding: .day, value: 1, to: repeatedDay))
    XCTAssertEqual(
      TaskRecurrenceDatePolicy.nextDueDate(from: due, rule: "daily", now: repeatedDay, calendar: calendar), repeatedDay)
    XCTAssertEqual(
      TaskRecurrenceDatePolicy.nextDueDate(
        from: due, rule: "daily", now: repeatedDay.addingTimeInterval(1), calendar: calendar), following)
    XCTAssertEqual(calendar.component(.day, from: following), 2)
  }

  func testExplicitCalendarDeterminesTheResultWithoutAmbientTimeZone() throws {
    let utc = try makeCalendar()
    let newYork = try makeCalendar(timeZone: "America/New_York")
    let kolkata = try makeCalendar(timeZone: "Asia/Kolkata")
    let due = try date(2026, 3, 7, calendar: newYork)
    let newYorkResult = TaskRecurrenceDatePolicy.nextDueDate(from: due, rule: "daily", now: due, calendar: newYork)
    let utcResult = TaskRecurrenceDatePolicy.nextDueDate(from: due, rule: "daily", now: due, calendar: utc)
    XCTAssertEqual(newYorkResult, try date(2026, 3, 8, calendar: newYork))
    XCTAssertEqual(utcResult, try date(2026, 3, 8, hour: 14, calendar: utc))
    XCTAssertNotEqual(newYorkResult, utcResult)
    XCTAssertEqual(
      TaskRecurrenceDatePolicy.nextDueDate(from: due, rule: "daily", now: due, calendar: kolkata), utcResult)
  }

  func testUnsupportedRulesDoNotPerformCalendarArithmetic() throws {
    let calendar = try makeCalendar()
    let due = try date(2026, 10, 9, calendar: calendar)
    for rule in ["", "yearly", "DAILY", "FREQ=DAILY"] {
      XCTAssertNil(
        TaskRecurrenceDatePolicy.nextDueDate(from: due, rule: rule, now: due, calendar: calendar) { _, _, _ in
          XCTFail("Unsupported rules must not invoke date arithmetic")
          return nil
        })
    }
  }

  func testNonfiniteDueDatesAndClockValuesAreRejectedBeforeArithmetic() throws {
    let calendar = try makeCalendar()
    let valid = try date(2026, 10, 9, calendar: calendar)
    for value in [Double.infinity, -Double.infinity, Double.nan] {
      let invalid = Date(timeIntervalSinceReferenceDate: value)
      for (due, now) in [(invalid, valid), (valid, invalid)] {
        XCTAssertNil(
          TaskRecurrenceDatePolicy.nextDueDate(from: due, rule: "weekdays", now: now, calendar: calendar) { _, _, _ in
            XCTFail("Nonfinite inputs must be rejected before calendar arithmetic")
            return nil
          })
      }
    }
  }

  func testMissingNonfiniteAndNonprogressingArithmeticResultsAreRejected() throws {
    let calendar = try makeCalendar()
    let due = try date(2026, 10, 9, calendar: calendar)
    let invalidResults: [Date?] = [
      nil, due, due.addingTimeInterval(-1),
      Date(timeIntervalSinceReferenceDate: .infinity), Date(timeIntervalSinceReferenceDate: .nan),
    ]
    for invalid in invalidResults {
      XCTAssertNil(
        TaskRecurrenceDatePolicy.nextDueDate(from: due, rule: "daily", now: due, calendar: calendar) { _, _, _ in
          invalid
        })
    }
  }

  func testMissingWeekdayArithmeticAfterTheFirstWeekendDayReturnsNilWithoutUnwrapping() throws {
    let calendar = try makeCalendar()
    let due = try date(2026, 10, 9, calendar: calendar)
    var calls = 0
    let result = TaskRecurrenceDatePolicy.nextDueDate(from: due, rule: "weekdays", now: due, calendar: calendar) {
      component, value, date in
      calls += 1
      return calls == 1 ? calendar.date(byAdding: component, value: value, to: date) : nil
    }
    XCTAssertNil(result)
    XCTAssertEqual(calls, 2)
  }

  func testCatchUpStopsWhenLaterArithmeticDoesNotAdvance() throws {
    let calendar = try makeCalendar()
    let due = try date(2026, 10, 1, calendar: calendar)
    let now = try date(2026, 10, 3, calendar: calendar)
    let first = try date(2026, 10, 2, calendar: calendar)
    var calls = 0
    XCTAssertNil(
      TaskRecurrenceDatePolicy.nextDueDate(from: due, rule: "daily", now: now, calendar: calendar) { _, _, _ in
        calls += 1
        return first
      })
    XCTAssertEqual(calls, 2)
  }

  @MainActor
  func testActualTasksStoreWrapperUsesTheInjectedClockAndCalendar() throws {
    let calendar = try makeCalendar(timeZone: "America/New_York")
    let due = try date(2026, 1, 31, calendar: calendar)
    let now = try date(2026, 3, 1, calendar: calendar)
    for rule in ["daily", "weekdays", "weekly", "biweekly", "monthly", "unsupported"] {
      XCTAssertEqual(
        TasksStore.shared.nextFutureDueDate(from: due, rule: rule, now: now, calendar: calendar),
        TaskRecurrenceDatePolicy.nextDueDate(from: due, rule: rule, now: now, calendar: calendar), rule)
    }
    XCTAssertEqual(
      TasksStore.shared.nextFutureDueDate(from: due, rule: "monthly", now: now, calendar: calendar),
      try date(2026, 3, 28, calendar: calendar))
  }

  private func makeCalendar(timeZone: String = "UTC") throws -> Calendar {
    var calendar = Calendar(identifier: .gregorian)
    calendar.locale = Locale(identifier: "en_US_POSIX")
    calendar.timeZone = try XCTUnwrap(TimeZone(identifier: timeZone))
    return calendar
  }

  private func date(
    _ year: Int, _ month: Int, _ day: Int, hour: Int = 9, minute: Int = 0, calendar: Calendar
  ) throws -> Date {
    try XCTUnwrap(calendar.date(from: DateComponents(year: year, month: month, day: day, hour: hour, minute: minute)))
  }
}
