import XCTest

@testable import Omi_Computer

/// Rewind's track spans retained history, while the day popover states the same boundary in words
/// and offers precise day jumps. These pin the two things that wording has to get right:
///
///  1. **Not-yet-surveyed is not "none".** The capture-day walk runs behind first paint; an empty
///     list before it finishes means "not looked yet". Printing "No screen capture yet" over an
///     account that has months of it is the same defect the spine's hour rail was already fixed for
///     (`nil` renders `—`, `0` renders zero) and it is cheap to reintroduce here.
///  2. **The span names its own cause.** A user who sees "3 days of capture" and no mention of the
///     retention setting reads a limit as a fact about themselves.
final class RewindHistoryReachTests: XCTestCase {

  /// One calendar builds the fixture days *and* names them, so the two can never disagree.
  ///
  /// The zone is `Asia/Tokyo` rather than the `America/New_York` the rest of this suite pins,
  /// because here the zone has to be *east* of UTC to do its job. These fixtures are start-of-day
  /// instants: Tokyo midnight on the 5th is 15:00 UTC on the **4th**, so a renderer that ignores the
  /// calendar it was handed and formats in the machine's zone prints "Aug 4" and fails — on the UTC
  /// CI runner and on a UTC-4 developer's machine alike. Pinning a zone west of UTC would leave
  /// local midnight on the same UTC calendar day and keep exactly that regression green everywhere.
  /// Resolved in `setUpWithError` rather than in a property initializer so a zone the system cannot
  /// resolve fails the test outright instead of quietly falling back to GMT — a GMT fallback would
  /// put local midnight back on the UTC calendar day and keep the regression above green.
  private var calendar = Calendar(identifier: .gregorian)

  override func setUpWithError() throws {
    try super.setUpWithError()
    calendar.timeZone = try XCTUnwrap(
      TimeZone(identifier: "Asia/Tokyo"),
      "the pinned fixture zone must exist in the system time zone database")
  }

  /// Pinned so the month names and digits asserted below are the ones this test was written against,
  /// rather than whatever language and numbering system the machine happens to be set to. Production
  /// deliberately keeps `Locale.current` — the label is read by the user, not by a machine.
  private let locale = Locale(identifier: "en_US_POSIX")

  /// Throws rather than traps: an unresolvable fixture date is this test's own setup failing, and a
  /// trap here takes the whole `xctest` process down with it and hides every result after it.
  private func day(_ year: Int, _ month: Int, _ dayOfMonth: Int) throws -> Date {
    var components = DateComponents()
    components.year = year
    components.month = month
    components.day = dayOfMonth
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
      days: [try day(2026, 8, 5)], surveyed: true, calendar: calendar, locale: locale)

    XCTAssertTrue(label.hasPrefix("1 day of capture"), "Got: \(label)")
    XCTAssertTrue(
      label.contains("Aug 5, 2026"),
      "the day must be named in the zone it was bucketed in, not the machine's, got: \(label)")
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

    let label = RewindHistoryReach.spanLabel(
      days: days, surveyed: true, calendar: calendar, locale: locale)

    XCTAssertTrue(label.hasPrefix("3 days of capture"), "Got: \(label)")
    XCTAssertTrue(label.contains("2026"), "Span must name real dates, got: \(label)")
    // Both ends named exactly, in the pinned zone: rendering these Tokyo midnights in the machine's
    // zone would say "Jul 1" and "Aug 4" instead, which is the day-off defect this pins down.
    XCTAssertTrue(label.contains("Jul 2, 2026"), "Got: \(label)")
    XCTAssertTrue(label.contains("Aug 5, 2026"), "Got: \(label)")
    // Oldest end first: the user is reading it as "from … to …". Unwrapped rather than `if let`,
    // because a lookup that finds nothing means the label stopped naming months — which is a
    // failure, not a reason to skip the check.
    let oldestRange = try XCTUnwrap(label.range(of: "Jul"), "Got: \(label)")
    let newestRange = try XCTUnwrap(label.range(of: "Aug"), "Got: \(label)")
    XCTAssertLessThan(
      oldestRange.lowerBound, newestRange.lowerBound,
      "The oldest end of the span must be stated first, got: \(label)")
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
