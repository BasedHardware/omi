import AppKit
import SwiftUI
import XCTest

@testable import Omi_Computer

@MainActor
final class SpineDayRecapTests: XCTestCase {
  private func tokyoCalendar() throws -> Calendar {
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = try XCTUnwrap(TimeZone(identifier: "Asia/Tokyo"))
    return calendar
  }

  private func day(
    _ calendar: Calendar, year: Int, month: Int, day: Int, hour: Int = 15,
    conversationCount: Int = 1
  ) -> SpineDay {
    let id =
      calendar.date(from: DateComponents(year: year, month: month, day: day, hour: hour))
      .map { calendar.startOfDay(for: $0) } ?? .distantPast
    return SpineDay(
      id: id, title: "Today", momentCount: 0, conversationCount: conversationCount, taskCount: 0,
      rows: [])
  }

  private func record(date: String, emoji: String = "🚀") -> DailySummaryRecord {
    DailySummaryRecord(
      id: "ds_1", date: date, headline: "A focused day", overview: "You shipped the recap.",
      dayEmoji: emoji,
      highlights: [DailySummaryRecord.Highlight(topic: "Launch", emoji: "📈", summary: "Shipped.")])
  }

  /// `SpineDay.id` is local start-of-day. A UTC formatter of that instant is the previous
  /// calendar date in Tokyo; looking up recaps with it would miss every day.
  func testDateKeyRoundTripsInATimezoneEastOfUTC() throws {
    let calendar = try tokyoCalendar()
    let dayID = try XCTUnwrap(
      calendar.date(from: DateComponents(year: 2026, month: 8, day: 23, hour: 0)))
    let start = calendar.startOfDay(for: dayID)
    XCTAssertEqual(SpineDayDateKey.string(from: start, calendar: calendar), "2026-08-23")

    let utc = DateFormatter()
    utc.timeZone = TimeZone(identifier: "UTC")
    utc.dateFormat = "yyyy-MM-dd"
    XCTAssertEqual(utc.string(from: start), "2026-08-22")
    XCTAssertNotEqual(
      utc.string(from: start), SpineDayDateKey.string(from: start, calendar: calendar))
  }

  func testEmptyGenerateAppearsOnlyWhenTheDayHasConversations() throws {
    let calendar = try tokyoCalendar()
    let now = try XCTUnwrap(
      calendar.date(from: DateComponents(year: 2026, month: 8, day: 23, hour: 21)))
    let withConversations = day(calendar, year: 2026, month: 8, day: 22, conversationCount: 2)
    let without = day(calendar, year: 2026, month: 8, day: 22, conversationCount: 0)

    XCTAssertEqual(
      SpineDayRecapContent.resolve(
        recap: nil, conversationCount: withConversations.conversationCount,
        dayID: withConversations.id, now: now, calendar: calendar, summaryHour: 22),
      .emptyGenerate)
    XCTAssertEqual(
      SpineDayRecapContent.resolve(
        recap: nil, conversationCount: without.conversationCount, dayID: without.id, now: now,
        calendar: calendar, summaryHour: 22),
      .hidden)
  }

  func testEmptyGenerateHidesForTodayBeforeTheSummaryHour() throws {
    let calendar = try tokyoCalendar()
    let now = try XCTUnwrap(
      calendar.date(from: DateComponents(year: 2026, month: 8, day: 23, hour: 15)))
    let today = day(calendar, year: 2026, month: 8, day: 23, conversationCount: 3)
    XCTAssertEqual(
      SpineDayRecapContent.resolve(
        recap: nil, conversationCount: today.conversationCount, dayID: today.id, now: now,
        calendar: calendar, summaryHour: 22),
      .hidden)
    let afterHour = try XCTUnwrap(
      calendar.date(from: DateComponents(year: 2026, month: 8, day: 23, hour: 22)))
    XCTAssertEqual(
      SpineDayRecapContent.resolve(
        recap: nil, conversationCount: today.conversationCount, dayID: today.id, now: afterHour,
        calendar: calendar, summaryHour: 22),
      .emptyGenerate)
  }

  func testRecapContentWinsOverTheEmptyState() throws {
    let calendar = try tokyoCalendar()
    let now = try XCTUnwrap(
      calendar.date(from: DateComponents(year: 2026, month: 8, day: 23, hour: 15)))
    let today = day(calendar, year: 2026, month: 8, day: 23, conversationCount: 1)
    let recap = record(date: "2026-08-23")
    XCTAssertEqual(
      SpineDayRecapContent.resolve(
        recap: recap, conversationCount: today.conversationCount, dayID: today.id, now: now,
        calendar: calendar, summaryHour: 22),
      .recap(recap))
  }

  func testRecapRowRendersForADayWithARecap() {
    let recap = record(date: "2026-08-23")
    let host = NSHostingView(
      rootView: SpineDayRecapRow(
        content: .recap(recap), dateKey: "2026-08-23", now: Date(),
        calendar: Calendar(identifier: .gregorian)
      )
      .frame(width: 420)
      .accessibilityIdentifier("spine-day-recap-host"))
    host.frame = NSRect(x: 0, y: 0, width: 420, height: 200)
    host.layoutSubtreeIfNeeded()
    XCTAssertGreaterThan(host.fittingSize.height, 40)
  }

  func testEmptyStateRowRendersTheGenerateAffordance() {
    let host = NSHostingView(
      rootView: SpineDayRecapRow(
        content: .emptyGenerate, dateKey: "2026-08-22", now: Date(),
        calendar: Calendar(identifier: .gregorian)
      )
      .frame(width: 420))
    host.frame = NSRect(x: 0, y: 0, width: 420, height: 80)
    host.layoutSubtreeIfNeeded()
    XCTAssertGreaterThan(host.fittingSize.height, 8)
    XCTAssertGreaterThan(host.fittingSize.width, 0)
  }

  func testHeaderHeightIsUnchangedWithAndWithoutARecapEmoji() {
    let day = SpineDay(
      id: Date(timeIntervalSince1970: 1_777_000_000), title: "Today", momentCount: 4,
      conversationCount: 1, taskCount: 0, rows: [])
    func height(emoji: String?) -> CGFloat {
      let host = NSHostingView(
        rootView: SpineDayHeader(day: day, isCollapsed: false, onToggle: {}, recapEmoji: emoji)
          .frame(width: 480))
      host.frame = NSRect(x: 0, y: 0, width: 480, height: 80)
      host.layoutSubtreeIfNeeded()
      return host.fittingSize.height
    }
    XCTAssertEqual(SpineMetrics.dayHeaderHeight, 34)
    XCTAssertEqual(height(emoji: nil), height(emoji: "🚀"), accuracy: 0.5)
  }
}
