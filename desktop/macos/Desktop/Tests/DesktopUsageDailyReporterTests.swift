import Foundation
import XCTest

@testable import Omi_Computer

@MainActor
final class DesktopUsageDailyReporterTests: XCTestCase {
  func testUsageReporterAccumulatesAndRollsOverWithoutDroppingPriorDay() throws {
    let suite = "DesktopUsageDailyReporterTests.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
    defer { defaults.removePersistentDomain(forName: suite) }
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = try XCTUnwrap(TimeZone(identifier: "America/New_York"))
    let dayOne = Date(timeIntervalSince1970: 1_788_230_400)
    let dayTwo = try XCTUnwrap(calendar.date(byAdding: .day, value: 1, to: dayOne))
    let reporter = DesktopUsageDailyReporter(
      defaults: defaults,
      now: { dayOne },
      calendar: calendar,
      timezone: { calendar.timeZone },
      deviceID: { "device-1" })

    reporter.sampleForTesting(watching: true, listening: false, at: dayOne)
    reporter.recordProactiveCardShown()
    reporter.recordProactiveCardActed()
    reporter.recordCompletedPTTTurn(repliedToCard: true)
    reporter.sampleForTesting(watching: true, listening: true, at: dayTwo)

    let snapshot = reporter.snapshotForTesting()
    let keys = snapshot.records.keys.sorted()
    XCTAssertEqual(keys.count, 2)
    XCTAssertEqual(snapshot.records[keys[0]]?.watchingSeconds, 60)
    XCTAssertEqual(snapshot.records[keys[1]]?.watchingSeconds, 60)
    XCTAssertEqual(snapshot.records[keys[1]]?.listeningSeconds, 60)
    XCTAssertEqual(snapshot.records[keys[0]]?.proactiveCardsShown, 1)
    XCTAssertEqual(snapshot.records[keys[0]]?.proactiveCardsActed, 2)
    XCTAssertEqual(snapshot.records[keys[0]]?.pttTurns, 1)
  }

  func testUsagePersistenceIsNamespacedByOwner() throws {
    let suite = "DesktopUsageDailyReporterTests.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
    defer { defaults.removePersistentDomain(forName: suite) }
    let ownerA = DesktopUsageDailyReporter(defaults: defaults, ownerID: { "owner-a" })
    ownerA.recordProactiveCardShown()
    let ownerB = DesktopUsageDailyReporter(defaults: defaults, ownerID: { "owner-b" })

    XCTAssertEqual(ownerA.snapshotForTesting().dirtyDates.count, 1)
    XCTAssertTrue(ownerB.snapshotForTesting().dirtyDates.isEmpty)
  }
}
