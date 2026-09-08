import XCTest

@testable import Omi_Computer

/// The recent-frames menu's row titles. The age is the part the reader acts
/// on — the send-time policy refuses frames past the freshness bound, so a
/// menu row must show distance, not a bare clock time that reads the same
/// whether the frame is twenty minutes or a day old.
@MainActor
final class RecentScreensMenuContentTests: XCTestCase {
  private let now = Date(timeIntervalSince1970: 1_800_000_000)

  private func row(ageSeconds: TimeInterval) throws -> RecentScreenFrameRow {
    try XCTUnwrap(
      RecentScreenFrameRow(
        screenshot: Screenshot(
          id: 1,
          timestamp: now.addingTimeInterval(-ageSeconds),
          appName: "Safari",
          windowTitle: "Safari window"
        )))
  }

  func testYoungFrameReadsAsJustNow() throws {
    XCTAssertEqual(try row(ageSeconds: 10).menuTitle(now: now), "Safari — just now")
  }

  func testMinutesOldFrameShowsMinutes() throws {
    XCTAssertEqual(try row(ageSeconds: 120).menuTitle(now: now), "Safari — 2m ago")
    XCTAssertEqual(try row(ageSeconds: 3_540).menuTitle(now: now), "Safari — 59m ago")
  }

  func testHoursOldFrameShowsHours() throws {
    XCTAssertEqual(try row(ageSeconds: 3_600).menuTitle(now: now), "Safari — 1h ago")
    XCTAssertEqual(try row(ageSeconds: 86_340).menuTitle(now: now), "Safari — 23h ago")
  }

  func testDayOldFrameShowsACalendarDateNotAClockTime() throws {
    // The one case a bare clock time lied: yesterday's frame reading "14:32"
    // is indistinguishable from one twenty minutes old.
    let title = try row(ageSeconds: 2 * 86_400).menuTitle(now: now)
    XCTAssertTrue(title.hasPrefix("Safari — "), title)
    XCTAssertFalse(title.contains("just now"), title)
    XCTAssertTrue(title.contains(","), "calendar date renders with a date component: \(title)")
  }
}
