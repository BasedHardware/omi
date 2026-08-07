import XCTest

@testable import Omi_Computer

/// Rewind is a one-day-at-a-time player, so "how far back does this go" is a question it answers in
/// words. These pin the two things that wording has to get right:
///
///  1. **Not-yet-surveyed is not "none".** The capture-day walk runs behind first paint; an empty
///     list before it finishes means "not looked yet". Printing "No screen capture yet" over an
///     account that has months of it is the same defect the spine's hour rail was already fixed for
///     (`nil` renders `—`, `0` renders zero) and it is cheap to reintroduce here.
///  2. **The span names its own cause.** A user who sees "3 days of capture" and no mention of the
///     retention setting reads a limit as a fact about themselves.
final class RewindHistoryReachTests: XCTestCase {

  private let calendar = Calendar(identifier: .gregorian)

  /// Throws rather than traps: an unresolvable fixture date is this test's own setup failing, and a
  /// trap here takes the whole `xctest` process down with it and hides every result after it.
  private func day(_ year: Int, _ month: Int, _ dayOfMonth: Int) throws -> Date {
    var components = DateComponents()
    components.year = year
    components.month = month
    components.day = dayOfMonth
    var calendar = self.calendar
    calendar.timeZone = .gmt
    return try XCTUnwrap(
      calendar.date(from: components), "\(year)-\(month)-\(dayOfMonth) must be a real date")
  }

  // MARK: - Unknown is never a confident zero

  func testUnsurveyedHistoryReadsAsCheckingRatherThanEmpty() {
    let label = RewindHistoryReach.spanLabel(days: [], surveyed: false, calendar: calendar)

    XCTAssertEqual(label, "Checking how far back your capture goes…")
    XCTAssertFalse(
      label.localizedCaseInsensitiveContains("no screen capture"),
      "A day range that has not been read yet must not be reported as an absence of capture")
  }

  func testUnsurveyedStateIsNotReachedOnceDaysAreKnown() throws {
    // The flag, not the emptiness, is what distinguishes the two. A populated list while the survey
    // is still running must still read as a real span, not as "checking".
    let label = RewindHistoryReach.spanLabel(
      days: [try day(2026, 8, 5)], surveyed: true, calendar: calendar)

    XCTAssertTrue(label.hasPrefix("1 day of capture"), "Got: \(label)")
  }

  func testSurveyedEmptyHistoryReadsAsNone() {
    XCTAssertEqual(
      RewindHistoryReach.spanLabel(days: [], surveyed: true, calendar: calendar),
      "No screen capture yet")
  }

  // MARK: - The span is the real span

  func testSpanNamesBothEndsAndTheDayCount() throws {
    // Newest first, as the walk produces them.
    let days = [try day(2026, 8, 5), try day(2026, 8, 4), try day(2026, 7, 2)]

    let label = RewindHistoryReach.spanLabel(days: days, surveyed: true, calendar: calendar)

    XCTAssertTrue(label.hasPrefix("3 days of capture"), "Got: \(label)")
    XCTAssertTrue(label.contains("2026"), "Span must name real dates, got: \(label)")
    // Oldest end first: the user is reading it as "from … to …".
    let oldestRange = label.range(of: "Jul")
    let newestRange = label.range(of: "Aug")
    if let oldestRange, let newestRange {
      XCTAssertLessThan(
        oldestRange.lowerBound, newestRange.lowerBound,
        "The oldest end of the span must be stated first, got: \(label)")
    }
  }

  // MARK: - The span names its cause

  func testRetentionNoteStatesTheDeletionWindow() {
    XCTAssertEqual(
      RewindHistoryReach.retentionNote(retentionDays: 7),
      "Capture older than 7 days is deleted")
    XCTAssertEqual(
      RewindHistoryReach.retentionNote(retentionDays: 1),
      "Capture older than 1 day is deleted")
  }

  func testRetentionNoteStatesWhenNothingIsDeleted() {
    XCTAssertEqual(
      RewindHistoryReach.retentionNote(retentionDays: RewindSettings.unlimitedRetentionDays),
      "Keeping everything — nothing is deleted")
  }
}
